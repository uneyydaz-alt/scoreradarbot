"""Value bet detector — The Odds API + Pinnacle comme référence de probabilité."""

import httpx
import logging
from datetime import datetime, timezone, timedelta
from config import ODDS_API_KEY

logger = logging.getLogger(__name__)

BASE_URL = "https://api.the-odds-api.com/v4"
MIN_EDGE = 0.04  # 4% minimum pour alerter

# Ligues principales (sport keys de The Odds API)
SOCCER_SPORTS = [
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_italy_serie_a",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one",
    "soccer_portugal_primeira_liga",
    "soccer_netherlands_eredivisie",
    "soccer_belgium_first_div",
    "soccer_uefa_champs_league",
    "soccer_uefa_europa_league",
    "soccer_uefa_europa_conference_league",
]

# Bookmakers souples à comparer contre Pinnacle
SOFT_BOOKS = ["bet365", "unibet", "betway", "williamhill", "bwin", "betclic"]


async def _fetch_sport_odds(sport: str, markets: str = "h2h,totals") -> list:
    if not ODDS_API_KEY:
        logger.warning("ODDS_API_KEY manquant dans .env")
        return []
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu,uk",
        "markets": markets,
        "oddsFormat": "decimal",
        "bookmakers": "pinnacle," + ",".join(SOFT_BOOKS),
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{BASE_URL}/sports/{sport}/odds", params=params)
        if r.status_code == 200:
            remaining = r.headers.get("x-requests-remaining", "?")
            logger.info("Odds API [%s] OK — %s requêtes restantes", sport, remaining)
            return r.json()
        elif r.status_code == 401:
            logger.error("Odds API: clé invalide (401)")
        elif r.status_code == 422:
            pass  # Sport sans matchs disponibles, normal
        else:
            logger.error("Odds API [%s] HTTP %d", sport, r.status_code)
    except Exception as e:
        logger.error("Odds API fetch error [%s]: %s", sport, e)
    return []


def _true_probs(outcomes: list) -> dict:
    """Retire la marge Pinnacle et retourne les probabilités réelles par outcome."""
    total_implied = sum(1 / o["price"] for o in outcomes if o["price"] > 1)
    if not total_implied:
        return {}
    return {o["name"]: (1 / o["price"]) / total_implied for o in outcomes}


def _analyze_match(match: dict, min_edge: float) -> list:
    """Retourne la liste des value bets trouvés sur un match."""
    books = {b["key"]: b for b in match.get("bookmakers", [])}
    pinnacle = books.get("pinnacle")
    if not pinnacle:
        return []

    # Probabilités réelles depuis Pinnacle (vig retirée)
    ref_probs = {}
    for mkt in pinnacle["markets"]:
        ref_probs[mkt["key"]] = _true_probs(mkt["outcomes"])

    found = []
    for book_key, book in books.items():
        if book_key == "pinnacle":
            continue
        for mkt in book["markets"]:
            mkey = mkt["key"]
            if mkey not in ref_probs:
                continue
            for outcome in mkt["outcomes"]:
                name = outcome["name"]
                soft_odds = outcome["price"]
                true_p = ref_probs[mkey].get(name)
                if not true_p or soft_odds <= 1:
                    continue

                edge = true_p * soft_odds - 1
                if edge < min_edge:
                    continue

                implied_p = 1 / soft_odds
                fair_odds = 1 / true_p

                if mkey == "h2h":
                    label = f"1X2 — {name}"
                elif mkey == "totals":
                    point = outcome.get("point", "")
                    label = f"{'Over' if name == 'Over' else 'Under'} {point}"
                else:
                    label = f"{mkey} — {name}"

                found.append({
                    "home":         match["home_team"],
                    "away":         match["away_team"],
                    "league":       match.get("sport_title", ""),
                    "kickoff":      match.get("commence_time", ""),
                    "market":       label,
                    "bookmaker":    book["title"],
                    "soft_odds":    round(soft_odds, 2),
                    "fair_odds":    round(fair_odds, 2),
                    "implied_prob": round(implied_p * 100, 2),
                    "true_prob":    round(true_p * 100, 2),
                    "edge":         round(edge * 100, 2),
                    "odds_low":     round(fair_odds * 0.96, 2),
                    "odds_high":    round(fair_odds * 1.06, 2),
                })

    return sorted(found, key=lambda x: x["edge"], reverse=True)


def format_value_bet(vb: dict) -> str:
    """Formate un value bet pour Telegram."""
    try:
        ko = datetime.fromisoformat(vb["kickoff"].replace("Z", "+00:00"))
        ko_str = ko.strftime("%d/%m %H:%M")
    except Exception:
        ko_str = "?"

    edge = vb["edge"]
    confidence = "Élevé 🔥" if edge >= 7 else "Moyen ✅" if edge >= 4 else "Faible"

    return (
        f"⚽ {vb['home']} vs {vb['away']}\n"
        f"🏆 {vb['league']} — {ko_str}\n"
        f"\n"
        f"📊 Value Bet détecté\n"
        f"• Marché : {vb['market']}\n"
        f"• Cote : {vb['soft_odds']} ({vb['bookmaker']})\n"
        f"• Probabilité implicite : {vb['implied_prob']}%\n"
        f"• Probabilité réelle : {vb['true_prob']}%\n"
        f"• Range de cote : {vb['odds_low']} – {vb['odds_high']}\n"
        f"\n"
        f"• Edge : +{edge}%\n"
        f"• Niveau de confiance : {confidence}\n"
        f"• Décision : BET ✅\n"
        f"\n"
        f"⚠️ Le long terme se construit sur la répétition d'edges positifs."
    )


async def get_value_bets(hours_ahead: int = 36, min_edge: float = MIN_EDGE) -> list:
    """Récupère tous les value bets pour les matchs dans les prochaines `hours_ahead` heures."""
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours_ahead)
    all_vbs = []

    for sport in SOCCER_SPORTS:
        matches = await _fetch_sport_odds(sport)
        for match in matches:
            try:
                ko = datetime.fromisoformat(match["commence_time"].replace("Z", "+00:00"))
                if ko < now or ko > cutoff:
                    continue
                all_vbs.extend(_analyze_match(match, min_edge))
            except Exception as e:
                logger.error("Value bet parse error: %s", e)

    # Dédupliquer (même match + même marché peut apparaître via plusieurs bookmakers)
    seen = set()
    unique = []
    for vb in sorted(all_vbs, key=lambda x: x["edge"], reverse=True):
        key = (vb["home"], vb["away"], vb["market"])
        if key not in seen:
            seen.add(key)
            unique.append(vb)

    logger.info("Value bets trouvés : %d (edge >= %.0f%%)", len(unique), min_edge * 100)
    return unique
