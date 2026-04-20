"""Analyseur de matchs — détection intelligente de buts imminents."""

import logging

logger = logging.getLogger(__name__)

# Cache des stats precedentes pour calcul du momentum
_prev_stats = {}  # fixture_id -> {"shots_on": X, "xg": Y, "dangerous": Z, "elapsed": E}

def _calc_momentum(fixture_id, elapsed, total_shots_on, total_xg, total_dangerous):
    """Calcule le momentum en comparant les stats avec le scan precedent."""
    prev = _prev_stats.get(fixture_id)
    momentum = 0.0

    if prev and elapsed > prev["elapsed"]:
        dt = elapsed - prev["elapsed"]
        if dt > 0 and dt <= 10:
            shots_delta = total_shots_on - prev["shots_on"]
            xg_delta = total_xg - prev["xg"]
            dangerous_delta = total_dangerous - prev["dangerous"]

            shots_rate = shots_delta / dt * 90
            xg_rate = xg_delta / dt * 90

            if shots_rate > 15:
                momentum += min((shots_rate - 15) / 20, 1.0) * 3
            if xg_rate > 2.0:
                momentum += min((xg_rate - 2.0) / 3.0, 1.0) * 3
            if dangerous_delta > 15:
                momentum += min((dangerous_delta - 15) / 20, 1.0) * 2

    _prev_stats[fixture_id] = {
        "shots_on": total_shots_on,
        "xg": total_xg,
        "dangerous": total_dangerous,
        "elapsed": elapsed,
    }

    return min(momentum, 8.0)


def _detect_match_profile(total_shots, total_fouls, total_corners, total_dangerous, elapsed):
    """Detecte le profil du match: ouvert, bloque, ou equilibre."""
    if elapsed < 15:
        return "early", 0

    shots_rate = total_shots / elapsed * 90

    if shots_rate > 22:
        return "open", 3
    if shots_rate < 10:
        return "blocked", -3

    return "balanced", 0


# Tranches de minutes avec pics de buts historiques (facteur 0-1)
GOAL_PEAKS = {
    (0, 15): 0.3,
    (16, 30): 0.5,
    (31, 45): 0.8,    # Fin de 1ère mi-temps
    (46, 60): 0.6,
    (61, 75): 0.8,
    (76, 90): 1.0,    # Fin de match = max de buts
}


def _safe_int(value) -> int:
    """Convertit une valeur en int, retourne 0 si impossible."""
    if value is None:
        return 0
    if isinstance(value, str):
        value = value.replace("%", "").strip()
        if not value:
            return 0
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0


def _get_goal_peak_factor(elapsed: int) -> float:
    """Retourne le facteur de pic de buts pour la tranche de minutes actuelle."""
    for (start, end), factor in GOAL_PEAKS.items():
        if start <= elapsed <= end:
            return factor
    return 0.3


def analyze_match(fixture_info, stats, prematch=None):
    """Analyse un match et retourne un signal si un but semble imminent.

    Logique basée sur :
    - Dette de xG (xG >> buts = le match va craquer)
    - Intensité offensive normalisée par minute
    - Pression dans la surface (tirs dans la box + arrêts)
    - Contexte temporel (pics historiques de buts)
    - Contexte du score (0-0 tard, score serré, etc.)
    - Données pré-match FootyStats
    """
    home = stats.get("home", {})
    away = stats.get("away", {})
    elapsed = fixture_info.get("elapsed", 0)

    if elapsed <= 5:
        return None  # Trop tôt pour analyser

    # --- Extraire les stats ---
    home_shots_on = _safe_int(home.get("Shots on Goal", 0))
    away_shots_on = _safe_int(away.get("Shots on Goal", 0))
    home_shots_total = _safe_int(home.get("Total Shots", 0))
    away_shots_total = _safe_int(away.get("Total Shots", 0))
    home_possession = _safe_int(home.get("Ball Possession", 0))
    away_possession = _safe_int(away.get("Ball Possession", 0))
    home_corners = _safe_int(home.get("Corner Kicks", 0))
    away_corners = _safe_int(away.get("Corner Kicks", 0))
    home_inside = _safe_int(home.get("Shots insidebox", 0))
    away_inside = _safe_int(away.get("Shots insidebox", 0))
    home_xg = float(home.get("expected_goals", 0) or 0)
    away_xg = float(away.get("expected_goals", 0) or 0)
    home_saves = _safe_int(home.get("Goalkeeper Saves", 0))
    away_saves = _safe_int(away.get("Goalkeeper Saves", 0))
    home_dangerous = _safe_int(home.get("Dangerous Attacks", 0))
    home_fouls = _safe_int(home.get("Fouls", 0))
    away_fouls = _safe_int(away.get("Fouls", 0))
    away_dangerous = _safe_int(away.get("Dangerous Attacks", 0))

    total_goals = fixture_info["home_goals"] + fixture_info["away_goals"]
    total_xg = home_xg + away_xg
    total_shots_on = home_shots_on + away_shots_on
    total_shots = home_shots_total + away_shots_total
    total_corners = home_corners + away_corners
    total_inside = home_inside + away_inside
    total_saves = home_saves + away_saves
    total_dangerous = home_dangerous + away_dangerous
    total_fouls = home_fouls + away_fouls

    # ==========================================
    # SCORE DE CONFIANCE (0-100)
    # ==========================================
    score = 0.0

    # ---- 1. DETTE DE XG (max 25 pts) ----
    # xG élevé mais peu de buts = le match va "craquer"
    xg_debt = total_xg - total_goals
    if xg_debt > 0:
        # 0.5 de dette = déjà significatif, 1.5+ = très fort
        score += min(xg_debt / 1.2, 1.0) * 25
    # Bonus si xG total élevé même avec des buts (match ouvert)
    if total_xg > 1.5:
        score += min((total_xg - 1.5) / 2.0, 1.0) * 5

    # ---- 2. INTENSITÉ OFFENSIVE NORMALISÉE (max 20 pts) ----
    # On compare les tirs cadrés au rythme attendu
    expected_shots_on = elapsed / 90 * 5  # ~5 tirs cadrés par match en moyenne
    if expected_shots_on > 0:
        intensity_ratio = total_shots_on / max(expected_shots_on, 0.5)
        score += min(intensity_ratio / 2.5, 1.0) * 20

    # ---- 3. PRESSION DANS LA SURFACE (max 15 pts) ----
    # Tirs dans la surface + arrêts du gardien = danger concret
    pressure = total_inside + total_saves
    # Normaliser par minute jouée
    pressure_per_min = pressure / max(elapsed, 1) * 90
    score += min(pressure_per_min / 15, 1.0) * 15

    # ---- 4. ATTAQUES DANGEREUSES (max 8 pts) ----
    if total_dangerous > 0:
        dangerous_per_min = total_dangerous / max(elapsed, 1) * 90
        score += min(dangerous_per_min / 120, 1.0) * 8

    # ---- 5. CORNERS (max 6 pts) ----
    corners_per_min = total_corners / max(elapsed, 1) * 90
    score += min(corners_per_min / 12, 1.0) * 6

    # ---- 6. DOMINATION UNILATÉRALE (max 6 pts) ----
    # Une équipe qui domine à 65%+ de possession pousse fort
    possession_diff = abs(home_possession - away_possession)
    if possession_diff > 15:
        score += min((possession_diff - 15) / 20, 1.0) * 6

    # ---- 6b. POSSESSION OFFENSIVE (max 4 pts) ----
    # Possession élevée des deux côtés = match ouvert
    max_poss = max(home_possession, away_possession)
    if max_poss >= 55:
        score += min((max_poss - 55) / 15, 1.0) * 4

    # ---- 6c. MOMENTUM — Rythme de tirs (max 5 pts) ----
    # Si beaucoup de tirs par rapport au temps écoulé = pression récente
    if elapsed > 15:
        shots_rate = total_shots / elapsed * 90  # tirs projetés sur 90 min
        if shots_rate > 20:  # Plus de 20 tirs/match = très offensif
            score += min((shots_rate - 20) / 15, 1.0) * 5


    # ---- 6d. MOMENTUM INTER-SCAN (max 8 pts) ----
    fixture_id = fixture_info.get("fixture_id", 0)
    momentum_pts = _calc_momentum(fixture_id, elapsed, total_shots_on, total_xg, total_dangerous)
    score += momentum_pts

    # ---- 6e. PROFIL DE MATCH (max +3 / -3 pts) ----
    match_profile, profile_bonus = _detect_match_profile(total_shots, total_fouls, total_corners, total_dangerous, elapsed)
    score += profile_bonus

    # ---- 7. CONTEXTE TEMPOREL (max 12 pts) ----
    peak_factor = _get_goal_peak_factor(elapsed)
    score += peak_factor * 12

    # ---- 8. CONTEXTE DU SCORE (max 12 pts) ----
    # 0-0 en 2ème mi-temps = tension maximale, un but va arriver
    if total_goals == 0 and elapsed > 55:
        score += min((elapsed - 55) / 20, 1.0) * 12
    elif total_goals == 0 and elapsed > 30:
        score += min((elapsed - 30) / 25, 1.0) * 8
    # Score serré en fin de match = les deux équipes poussent
    elif abs(fixture_info["home_goals"] - fixture_info["away_goals"]) <= 1 and elapsed > 60:
        score += min((elapsed - 60) / 15, 1.0) * 8
    # Match déjà ouvert (2+ buts) avec xG dette positive
    elif total_goals >= 2 and xg_debt > 0.3:
        score += 5

    # ---- 9. FOOTYSTATS PRÉ-MATCH (max 12 pts) ----
    if prematch:
        pm_score = 0.0
        avg_goals = prematch.get("avg_potential", 0)
        if avg_goals > 2.0:
            pm_score += min((avg_goals - 2.0) / 1.5, 1.0) * 5

        btts = prematch.get("btts_potential", 0)
        if btts > 50:
            pm_score += min((btts - 50) / 30, 1.0) * 4

        odds_over25 = prematch.get("odds_ft_over25", 0)
        if 0 < odds_over25 < 2.0:
            pm_score += (2.0 - odds_over25) / 1.0 * 3

        score += min(pm_score, 12)
    else:
        # Pas de données FootyStats — bonus par défaut pour ligues populaires
        score += 12

    # ==========================================
    # BONUS COMBINÉS — Situations à forte probabilité
    # ==========================================

    # 0-0 + haute dette xG + fin de match = combo très fort
    if total_goals == 0 and xg_debt > 0.8 and elapsed > 60:
        score += 10

    # Beaucoup de tirs cadrés sans but = gardien en feu mais ça va lâcher
    if total_shots_on >= 6 and total_goals <= 1:
        score += 5

    # Pression massive (saves + inside box + corners élevés ensemble)
    if total_saves >= 4 and total_inside >= 5 and total_corners >= 5:
        score += 5

    # ==========================================
    # FILTRES — Ne pas alerter dans ces cas
    # ==========================================

    # Match déjà très scoré (5+ buts) et xG "payé"
    if total_goals >= 5 and xg_debt < 0.3:
        return None

    # Match trop calme (aucun tir en 25+ minutes)
    if elapsed > 25 and total_shots < 1:
        return None

    # Mi-temps (pas de données utiles pendant la pause)
    status = fixture_info.get("status", "")
    if status in ("HT", "BT"):
        return None

    # ==========================================
    # CARTONS ROUGES — Pénalité si équipe dominante a un rouge
    # ==========================================
    home_reds = 0
    away_reds = 0
    if stats:
        hr = stats.get("home", {}).get("Red Cards", 0)
        ar = stats.get("away", {}).get("Red Cards", 0)
        home_reds = int(hr) if hr else 0
        away_reds = int(ar) if ar else 0

    confidence = min(int(score), 100)

    # --- Déterminer l'équipe dominante ---
    home_dominance = home_shots_on * 2 + home_inside + home_xg * 4 + home_corners + home_dangerous * 0.02
    away_dominance = away_shots_on * 2 + away_inside + away_xg * 4 + away_corners + away_dangerous * 0.02

    # Carton rouge = réduire la dominance de l'équipe à 10
    if home_reds > 0:
        home_dominance *= 0.4  # -60% dominance
    if away_reds > 0:
        away_dominance *= 0.4  # -60% dominance

    if home_dominance >= away_dominance:
        dominant_team = fixture_info["home_team"]
        dominant_side = "home"
    else:
        dominant_team = fixture_info["away_team"]
        dominant_side = "away"

    logger.info(
        "%s %d-%d %s (%d') → conf: %d | xG: %.2f dette: %.2f | tirs: %d/%d | saves: %d%s",
        fixture_info["home_team"], fixture_info["home_goals"],
        fixture_info["away_goals"], fixture_info["away_team"],
        elapsed, confidence, total_xg, xg_debt,
        total_shots_on, total_shots, total_saves,
        " [FS]" if prematch else "",
    )
    if home_reds or away_reds:
        logger.info(
            "  🟥 Cartons rouges: %s=%d, %s=%d",
            fixture_info["home_team"], home_reds,
            fixture_info["away_team"], away_reds,
    )

    # Calcul des fenêtres et cotes
    entry_start = max(elapsed + 2, 1)
    entry_end = min(elapsed + 8, 90)
    goal_window_start = min(elapsed + 3, 90)
    goal_window_end = min(elapsed + 15, 90)

    prob_short = min(confidence + 8, 99) if elapsed < 60 else min(confidence + 5, 99)
    prob_full_match = min(confidence + 12, 99)

    # Cotes estimées
    optimal_odds = round(1 / max(confidence / 100, 0.3), 2)
    aggressive_odds = round(optimal_odds * 1.6, 2)

    # Mise suggérée
    optimal_stake = "1.0F" if confidence >= 80 else "0.5F"
    aggressive_stake = "0.4F" if confidence >= 80 else "0.2F"

    return {
        "fixture_info": fixture_info,
        "confidence": confidence,
        "dominant_team": dominant_team,
        "dominant_side": dominant_side,
        "stats": {
            "home_shots_on": home_shots_on,
            "away_shots_on": away_shots_on,
            "home_possession": home_possession,
            "away_possession": away_possession,
            "home_corners": home_corners,
            "away_corners": away_corners,
            "home_xg": home_xg,
            "away_xg": away_xg,
        },
        "home_reds": home_reds,
        "away_reds": away_reds,
        "momentum": momentum_pts,
        "match_profile": match_profile,
        "prematch": prematch or {},
        "context": _generate_context(
            fixture_info, stats, dominant_team, dominant_side,
            elapsed, xg_debt, total_shots_on, total_saves,
        ),
        "trading": {
            "entry_start": entry_start,
            "entry_end": entry_end,
            "goal_window_start": goal_window_start,
            "goal_window_end": goal_window_end,
            "optimal_odds": optimal_odds,
            "aggressive_odds": aggressive_odds,
            "optimal_stake": optimal_stake,
            "aggressive_stake": aggressive_stake,
            "prob_before_70": prob_short,
            "prob_full_match": prob_full_match,
        },
    }


def _generate_context(
    fixture_info: dict, stats: dict, dominant: str, side: str,
    elapsed: int, xg_debt: float, total_shots_on: int, total_saves: int,
) -> str:
    """Génère le texte de contexte pour l'alerte."""
    possession = stats.get(side, {}).get("Ball Possession", "?")
    parts = []

    # Analyse de la dette xG
    if xg_debt > 0.5:
        parts.append(
            f"Le xG ({xg_debt:+.2f} au-dessus du score) indique que les occasions sont la "
            f"mais le score ne suit pas encore."
        )

    # Domination
    parts.append(f"{dominant} domine avec {possession} de possession.")

    # Pression
    if total_saves >= 3:
        parts.append(f"Les gardiens sont sollicites ({total_saves} arrets combines).")
    if total_shots_on >= 5:
        parts.append(f"Intensite offensive elevee ({total_shots_on} tirs cadres).")

    # Contexte temporel
    total_goals = fixture_info["home_goals"] + fixture_info["away_goals"]
    if total_goals == 0 and elapsed > 40:
        parts.append("Match sans but, la pression monte.")
    elif abs(fixture_info["home_goals"] - fixture_info["away_goals"]) <= 1 and elapsed > 65:
        parts.append("Score serre en fin de match, les deux equipes poussent.")

    for (start, end), factor in GOAL_PEAKS.items():
        if start <= elapsed <= end and factor >= 0.7:
            parts.append(f"Tranche {start}'-{end}' = pic historique de buts.")
            break

    return " ".join(parts)



def format_signal(signal: dict, lang: str = "fr") -> str:
    """Formate un signal en message Telegram."""
    info = signal["fixture_info"]
    s = signal["stats"]
    t = signal["trading"]
    conf = signal["confidence"]

    # Barre de progression
    filled = conf // 4
    bar = "\u2588" * filled + "\u2591" * (25 - filled)

    # Label confiance
    if conf >= 75:
        conf_label = "Signal fort"
    elif conf >= 60:
        conf_label = "Signal moyen"
    else:
        conf_label = "Signal faible"

    pm = signal.get("prematch", {})
    xg_home = f"{s['home_xg']:.2f}" if s["home_xg"] > 0 else "nd"
    xg_away = f"{s['away_xg']:.2f}" if s["away_xg"] > 0 else "nd"

    # Red card line
    home_reds = signal.get("home_reds", 0)
    away_reds = signal.get("away_reds", 0)
    red_card_line = ""
    if home_reds > 0 or away_reds > 0:
        red_card_line = "\U0001f7e5 Cartons rouges : " + str(home_reds) + " \u2013 " + str(away_reds)

    # Prematch line
    prematch_line = ""
    if pm:
        parts = []
        odds_over25 = pm.get("odds_ft_over25", 0)
        btts = pm.get("btts_potential", 0)
        if odds_over25 > 0:
            parts.append(f"Over 2.5 @{odds_over25:.2f}")
        if btts > 0:
            parts.append(f"BTTS {btts:.0f}%")
        if parts:
            joined = " \u00b7 ".join(parts)
            prematch_line = "\U0001f4cc Pr\u00e9-match : " + joined

    # Wrap context text
    import textwrap
    ctx = signal["context"]
    wrapped_ctx = "\n".join(textwrap.wrap(ctx, width=42))

    total_goals = info["home_goals"] + info["away_goals"]
    elapsed = info["elapsed"]
    base_over = total_goals + 0.5
    in_first_half = elapsed <= 45
    late_first_half = elapsed >= 40

    # --- Pick prioritaire: Over adaptatif ---
    if base_over >= 1.5:
        pick_prio = f"Over {base_over:.1f} FT"
    elif in_first_half and not late_first_half:
        pick_prio = f"Over {base_over:.1f} MT"
    elif in_first_half and late_first_half and conf >= 80:
        pick_prio = f"Over {base_over:.1f} MT"
    else:
        higher_over = total_goals + 1.5
        pick_prio = f"Over {higher_over:.1f} FT"
    pick_prio_stake = t["optimal_stake"]

    # --- Pick equipe: Over X.5 de l'equipe dominante ---
    dom_side = signal["dominant_side"]
    dom_goals = info["home_goals"] if dom_side == "home" else info["away_goals"]
    team_over = dom_goals + 0.5
    team_pick = f"Over {team_over:.1f} {signal['dominant_team']}"
    team_pick_stake = "0.3F"

    # --- Pick agressif: Prochain but equipe ---
    agg_pick = f"Prochain but \u2014 {signal['dominant_team']}"
    agg_stake = t["aggressive_stake"]

    sep = "\u2500" * 26
    thick_sep = "\u2501" * 28

    lines = []
    lines.append("\u25c9 GOAL SIGNAL")
    lines.append(thick_sep)
    lines.append("\U0001f3c6 " + info["league_name"].upper())
    lines.append(thick_sep)
    lines.append(info["home_team"] + "  " + str(info["home_goals"]) + " \u2013 " + str(info["away_goals"]) + "  " + info["away_team"])
    lines.append("\u25cf LIVE \u00b7 " + str(elapsed) + "'")
    lines.append(sep)

    # DONNEES CLES
    lines.append("\U0001f4ca DONN\u00c9ES CL\u00c9S")
    lines.append("\U0001f3af Tirs cadr\u00e9s : " + str(s["home_shots_on"]) + " \u2013 " + str(s["away_shots_on"]))
    lines.append("\U0001f4c9 xG : " + xg_home + " \u2013 " + xg_away)
    if red_card_line:
        lines.append(red_card_line)
    # Momentum indicator
    momentum = signal.get("momentum", 0)
    profile = signal.get("match_profile", "balanced")
    profile_icons = {"open": "\U0001f525 Match ouvert", "blocked": "\U0001f512 Match bloqu\u00e9", "balanced": "\u2696\ufe0f Match \u00e9quilibr\u00e9", "early": ""}
    profile_str = profile_icons.get(profile, "")
    if profile_str:
        lines.append(profile_str)
    if momentum >= 3:
        lines.append("\U0001f4c8 Momentum en hausse")
    if prematch_line:
        lines.append(prematch_line)
    lines.append(sep)

    # ANALYSE
    lines.append("\U0001f9e0 ANALYSE")
    lines.append(wrapped_ctx)
    lines.append(sep)

    # PLAN D'ENTREE
    lines.append("\U0001f3af PLAN D'ENTR\u00c9E")
    lines.append("")
    lines.append("\U0001f4cd Entr\u00e9e : " + str(t["entry_start"]) + "' \u2013 " + str(t["entry_end"]) + "'")
    lines.append("\u23f3 Fen\u00eatre : " + str(t["goal_window_start"]) + "' \u2013 " + str(t["goal_window_end"]) + "'")
    lines.append("")
    lines.append("\U0001f4c8 Probabilit\u00e9s")
    lines.append("\u251c Avant 70' : " + str(t["prob_before_70"]) + "%")
    lines.append("\u2514 Avant la fin : " + str(t["prob_full_match"]) + "%")
    lines.append("")
    lines.append("\U0001f48e Pick prioritaire")
    lines.append("\u2192 " + pick_prio + " \u00b7 " + pick_prio_stake)
    lines.append("")
    lines.append("\u26bd Pick \u00e9quipe")
    lines.append("\u2192 " + team_pick + " \u00b7 " + team_pick_stake)
    lines.append("")
    lines.append("\u26a0\ufe0f Pick agressif")
    lines.append("\u2192 " + agg_pick + " \u00b7 " + agg_stake)
    lines.append(sep)

    # CONFIANCE
    lines.append("\U0001f512 Confiance : " + str(conf) + "/100 \u00b7 " + conf_label)
    lines.append(bar + " " + str(conf) + "%")

    return "\n".join(lines)

