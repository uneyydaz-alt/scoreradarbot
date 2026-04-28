"""Analyse approfondie d'un match — foot (Pinnacle + Poisson) ou tennis (RapidAPI)."""

import asyncio
import httpx
import logging
import math
from datetime import datetime, timezone, timedelta

from config import ODDS_API_KEYS, SOFT_BOOKS

logger = logging.getLogger(__name__)

TENNIS_HOST = "tennisapi1.p.rapidapi.com"
TENNIS_BASE = f"https://{TENNIS_HOST}/api/tennis"

FOOTBALL_KEYWORDS = {
    "fc", "cf", "sc", "ac", "rc", "as", "ss", "us", "sk", "fk", "nk", "bk",
    "united", "city", "rovers", "wanderers", "athletic", "atletico", "real",
    "sporting", "juventus", "milan", "inter", "roma", "lazio", "napoli",
    "psg", "lyon", "marseille", "monaco", "arsenal", "chelsea", "liverpool",
    "tottenham", "everton", "leicester", "barcelona", "sevilla", "valencia",
    "betis", "ajax", "psv", "feyenoord", "porto", "benfica", "braga",
    "anderlecht", "bruges", "gent", "dortmund", "leipzig", "leverkusen",
    "rangers", "celtic", "hotspur", "wolves", "palace",
}

ALL_FOOTBALL_SPORTS = [
    "soccer_epl", "soccer_spain_la_liga", "soccer_france_ligue_one",
    "soccer_uefa_champs_league", "soccer_germany_bundesliga",
    "soccer_portugal_primeira_liga", "soccer_netherlands_eredivisie",
    "soccer_uefa_europa_league", "soccer_belgium_first_div",
    "soccer_italy_serie_a",
]

# Abréviations → mots-clés qui apparaissent dans le nom API
TEAM_ALIASES: dict[str, list[str]] = {
    "psg":          ["paris saint-germain", "paris sg"],
    "man utd":      ["manchester united"],
    "man united":   ["manchester united"],
    "man city":     ["manchester city"],
    "barca":        ["barcelona", "fc barcelona"],
    "barça":        ["barcelona", "fc barcelona"],
    "atleti":       ["atletico madrid", "atlético"],
    "atletico":     ["atletico madrid", "atlético"],
    "inter":        ["inter milan", "internazionale"],
    "juve":         ["juventus"],
    "juventus":     ["juventus"],
    "napoli":       ["napoli", "ssc napoli"],
    "milan":        ["ac milan"],
    "ac milan":     ["ac milan"],
    "real":         ["real madrid"],
    "ajax":         ["ajax"],
    "dortmund":     ["dortmund", "borussia dortmund"],
    "bvb":          ["borussia dortmund"],
    "leverkusen":   ["bayer leverkusen"],
    "leipzig":      ["rb leipzig"],
    "lyon":         ["olympique lyonnais", "lyon"],
    "marseille":    ["olympique de marseille", "marseille"],
    "porto":        ["fc porto"],
    "benfica":      ["sl benfica", "benfica"],
    "celtic":       ["celtic"],
    "rangers":      ["rangers"],
    "wolves":       ["wolverhampton"],
    "spurs":        ["tottenham"],
    "palace":       ["crystal palace"],
    "leicester":    ["leicester city"],
    "newcastle":    ["newcastle united"],
    "brighton":     ["brighton"],
    "villa":        ["aston villa"],
    "west ham":     ["west ham united"],
    "chelsea":      ["chelsea"],
    "arsenal":      ["arsenal"],
    "liverpool":    ["liverpool"],
    "everton":      ["everton"],
    "bayern":       ["fc bayern", "bayern munich", "bayern münchen"],
    "feyenoord":    ["feyenoord"],
    "psv":          ["psv eindhoven"],
    "anderlecht":   ["rsc anderlecht"],
    "bruges":       ["club brugge", "bruges"],
    "braga":        ["sc braga"],
    "sevilla":      ["sevilla fc"],
    "valencia":     ["valencia cf"],
    "villarreal":   ["villarreal"],
    "sociedad":     ["real sociedad"],
}


_NORMALIZE = str.maketrans("àáâãäåæçèéêëìíîïðñòóôõöùúûüýÿ",
                           "aaaaaааceeeeiiiiðnoooooуuuuуy")


def _norm(s: str) -> str:
    """Normalise : minuscule + accents retirés."""
    return s.lower().translate(_NORMALIZE)


def _resolve_aliases(name: str) -> list[str]:
    """Retourne les variantes connues d'un nom d'équipe (normalisées)."""
    key = _norm(name.strip())
    variants = [key]
    if key in TEAM_ALIASES:
        variants.extend([_norm(v) for v in TEAM_ALIASES[key]])
    # Cherche aussi une correspondance partielle dans les clés
    for alias_key, alias_vals in TEAM_ALIASES.items():
        if alias_key in key or key in alias_key:
            variants.extend([_norm(v) for v in alias_vals])
    return list(dict.fromkeys(variants))


def _match_team(search: str, api_name: str) -> bool:
    """Vérifie si search correspond à api_name (fuzzy + aliases + normalisation)."""
    api_n = _norm(api_name)
    for variant in _resolve_aliases(search):
        if variant in api_n or api_n in variant:
            return True
    # Matching mot-à-mot : chaque mot significatif du search dans le nom API
    sig_words = [w for w in _norm(search).split() if len(w) > 3]
    if sig_words and all(w in api_n for w in sig_words):
        return True
    return False

TENNIS_SPORTS = [
    "tennis_atp_french_open", "tennis_wta_french_open",
    "tennis_atp_us_open", "tennis_wta_us_open",
    "tennis_atp_wimbledon", "tennis_wta_wimbledon",
    "tennis_atp_aus_open", "tennis_wta_aus_open",
    "tennis_atp_single_clay", "tennis_atp_single_hard",
    "tennis_atp_single_grass", "tennis_wta_single",
]


# ── Sport detection ────────────────────────────────────────────────────────────

def is_tennis(home: str, away: str) -> bool:
    combined = (home + " " + away).lower()
    for kw in FOOTBALL_KEYWORDS:
        if kw in combined.split():
            return False
    # Joueurs tennis = max 2 mots chacun, pas d'indicateur club
    return len(home.split()) <= 3 and len(away.split()) <= 3


# ── Poisson helpers ────────────────────────────────────────────────────────────

def _pois(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(min(k, 20))


def _solve_lambda(p_over: float, line: float = 2.5) -> float:
    """Bisection : trouve λ tel que P(Poisson(λ) > line) = p_over."""
    lo, hi = 0.05, 12.0
    threshold = int(line) + 1
    for _ in range(60):
        mid = (lo + hi) / 2
        p = 1.0 - sum(_pois(k, mid) for k in range(threshold))
        if p < p_over:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _score_matrix(lh: float, la: float, top: int = 6) -> list[tuple]:
    """Top N scores les plus probables (home, away, proba%)."""
    scores = []
    for i in range(8):
        for j in range(8):
            p = _pois(i, lh) * _pois(j, la)
            scores.append((i, j, round(p * 100, 2)))
    scores.sort(key=lambda x: x[2], reverse=True)
    return scores[:top]


def _poisson_from_probs(p_home: float, p_over25: float) -> tuple[float, float]:
    """Estime λh, λa depuis P(home win) et P(over 2.5)."""
    lam_total = _solve_lambda(p_over25, 2.5)
    # Ratio home/away: calibré empiriquement sur la force relative
    # p_home ≈ 0.45 → ratio 1.35, p_home ≈ 0.30 → ratio 0.85
    ratio = 0.6 + 1.5 * p_home  # heuristique linéaire
    lh = lam_total * ratio / (1 + ratio)
    la = lam_total / (1 + ratio)
    return round(lh, 2), round(la, 2)


# ── Odds API helpers ───────────────────────────────────────────────────────────

def _active_key():
    from odds_client import _active_key as ak
    return ak()


async def _fetch_odds(sport: str, markets: str = "h2h,totals") -> list:
    from odds_client import _fetch
    return await _fetch(sport, markets)


async def _find_match_odds(home: str, away: str) -> dict | None:
    """Cherche un match dans toutes les ligues foot (fuzzy + aliases)."""
    for sport in ALL_FOOTBALL_SPORTS:
        for match in await _fetch_odds(sport):
            mh = match.get("home_team", "")
            ma = match.get("away_team", "")
            if _match_team(home, mh) and _match_team(away, ma):
                return match
            if _match_team(away, mh) and _match_team(home, ma):
                return match
    return None


async def _find_tennis_odds(p1: str, p2: str) -> dict | None:
    """Cherche un match tennis dans The Odds API (fuzzy)."""
    for sport in TENNIS_SPORTS:
        for match in await _fetch_odds(sport, "h2h"):
            mh = match.get("home_team", "")
            ma = match.get("away_team", "")
            if _match_team(p1, mh) and _match_team(p2, ma):
                return match
            if _match_team(p2, mh) and _match_team(p1, ma):
                return match
    return None


# ── Tennis RapidAPI ────────────────────────────────────────────────────────────

async def _tennis_get(path: str, key: str) -> dict | list:
    headers = {"x-rapidapi-host": TENNIS_HOST, "x-rapidapi-key": key}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{TENNIS_BASE}{path}", headers=headers)
        if r.status_code == 200:
            return r.json()
        logger.error("Tennis API HTTP %d %s", r.status_code, path)
    except Exception as e:
        logger.error("Tennis API error %s: %s", path, e)
    return {}


async def _search_player(name: str, key: str) -> dict | None:
    encoded = name.replace(" ", "%20")
    data = await _tennis_get(f"/player/search/{encoded}", key)
    items = data if isinstance(data, list) else (data.get("athletes") or data.get("results") or [])
    if items:
        return items[0]
    return None


def _extract_recent_results(results_data, n: int = 5) -> list[dict]:
    items = results_data if isinstance(results_data, list) else (
        results_data.get("events") or results_data.get("results") or []
    )
    out = []
    for r in items[:n]:
        try:
            winner = r.get("winner", {}) or {}
            competitors = r.get("sport_event", {}).get("competitors", []) or r.get("competitors", [])
            tournament = (r.get("sport_event", {}).get("sport_event_context", {})
                         .get("competition", {}).get("name", "")) or r.get("tournament", {}).get("name", "?")
            score = ""
            if r.get("sport_event_status"):
                score = r["sport_event_status"].get("display_score", "")
            out.append({"tournament": tournament, "score": score, "winner_id": winner.get("id", "")})
        except Exception:
            continue
    return out


# ── Public API ─────────────────────────────────────────────────────────────────

async def analyze_football(home: str, away: str) -> dict:
    """Analyse complète d'un match foot via The Odds API + modèle Poisson."""
    match = await _find_match_odds(home, away)
    if not match:
        return {"error": f"Match introuvable : {home} vs {away}"}

    books = {b["key"]: b for b in match.get("bookmakers", [])}
    pinnacle = books.get("pinnacle")
    if not pinnacle:
        return {"error": "Pinnacle introuvable pour ce match"}

    # Construire ref Pinnacle
    ref_probs = {}
    ref_raw = {}
    for mkt in pinnacle["markets"]:
        total = sum(1 / o["price"] for o in mkt["outcomes"] if o["price"] > 1)
        if not total:
            continue
        ref_probs[mkt["key"]] = {o["name"]: (1 / o["price"]) / total for o in mkt["outcomes"]}
        ref_raw[mkt["key"]] = {o["name"]: o["price"] for o in mkt["outcomes"]}

    h2h_probs = ref_probs.get("h2h", {})
    p_home = h2h_probs.get(match["home_team"], 0)
    p_draw = h2h_probs.get("Draw", 0)
    p_away = h2h_probs.get(match["away_team"], 0)

    # Totals 2.5
    totals_probs = ref_probs.get("totals", {})
    p_over25 = next((v for k, v in totals_probs.items() if "over" in k.lower()), None)
    ou_line = None
    for mkt in pinnacle["markets"]:
        if mkt["key"] == "totals":
            for o in mkt["outcomes"]:
                if o["name"].lower() == "over":
                    ou_line = o.get("point")
    if ou_line is None:
        ou_line = 2.5

    # Modèle Poisson
    lh, la = None, None
    top_scores = []
    if p_over25 and p_home:
        lh, la = _poisson_from_probs(p_home, p_over25)
        top_scores = _score_matrix(lh, la)

    # Meilleurs odds par outcome sur tous les soft books
    best_odds: dict[str, dict] = {}
    all_edges: list[dict] = []

    for bkey, book in books.items():
        if bkey == "pinnacle":
            continue
        for mkt in book["markets"]:
            mkey = mkt["key"]
            if mkey not in ref_probs:
                continue
            for outcome in mkt["outcomes"]:
                name = outcome["name"]
                soft = outcome["price"]
                true_p = ref_probs[mkey].get(name)
                if not true_p or soft <= 1:
                    continue
                edge = round((true_p * soft - 1) * 100, 2)
                pt = outcome.get("point", "")
                label = f"1X2 — {name}" if mkey == "h2h" else (
                    f"{'Over' if name == 'Over' else 'Under'} {pt}" if mkey == "totals"
                    else f"{mkey} — {name}"
                )
                entry = {
                    "market": label,
                    "bookmaker": book["title"],
                    "soft_odds": round(soft, 2),
                    "fair_odds": round(1 / true_p, 2),
                    "true_prob": round(true_p * 100, 1),
                    "edge": edge,
                }
                uid = f"{mkey}_{name}_{pt}"
                if uid not in best_odds or soft > best_odds[uid]["soft_odds"]:
                    best_odds[uid] = entry
                all_edges.append(entry)

    best_list = sorted(best_odds.values(), key=lambda x: x["edge"], reverse=True)

    try:
        ko = datetime.fromisoformat(match.get("commence_time", "").replace("Z", "+00:00"))
    except Exception:
        ko = None

    return {
        "sport": "football",
        "home": match["home_team"],
        "away": match["away_team"],
        "league": match.get("sport_title", ""),
        "kickoff": ko,
        "pinnacle_1x2": {
            "home": round(p_home * 100, 1),
            "draw": round(p_draw * 100, 1),
            "away": round(p_away * 100, 1),
        },
        "pinnacle_raw_1x2": ref_raw.get("h2h", {}),
        "over_line": ou_line,
        "p_over": round((p_over25 or 0) * 100, 1),
        "p_under": round((1 - (p_over25 or 0)) * 100, 1),
        "lambda_home": lh,
        "lambda_away": la,
        "top_scores": top_scores,
        "best_odds": best_list[:8],
    }


async def analyze_tennis(p1: str, p2: str, tennis_key: str) -> dict:
    """Analyse complète d'un match tennis via RapidAPI + The Odds API."""
    # 1. Recherche joueurs
    player1, player2 = await asyncio.gather(
        _search_player(p1, tennis_key),
        _search_player(p2, tennis_key),
    )
    if not player1 or not player2:
        missing = p1 if not player1 else p2
        return {"error": f"Joueur introuvable : {missing}"}

    p1_id = str(player1.get("id") or player1.get("competitor_id") or "")
    p2_id = str(player2.get("id") or player2.get("competitor_id") or "")

    # 2. Fetch H2H + résultats récents en parallèle
    h2h_raw, p1_res_raw, p2_res_raw = await asyncio.gather(
        _tennis_get(f"/player/h2h/{p1_id}/{p2_id}", tennis_key),
        _tennis_get(f"/player/{p1_id}/results", tennis_key),
        _tennis_get(f"/player/{p2_id}/results", tennis_key),
    )

    # 3. Cotes The Odds API
    odds_match = await _find_tennis_odds(p1, p2)

    # 4. Parser H2H
    h2h_list = h2h_raw if isinstance(h2h_raw, list) else (
        h2h_raw.get("last_meetings") or h2h_raw.get("meetings") or []
    )
    h2h_p1_wins = 0
    h2h_p2_wins = 0
    h2h_recent = []
    p1_name_lower = player1.get("name", p1).lower()
    for meeting in h2h_list[:10]:
        try:
            winner = meeting.get("winner", {}) or {}
            winner_id = str(winner.get("id", winner.get("competitor_id", "")))
            tournament = meeting.get("tournament", {}).get("name", "?")
            score_raw = meeting.get("sport_event_status", {}).get("display_score", "")
            if winner_id == p1_id:
                h2h_p1_wins += 1
                label = f"✅ {player1.get('name', p1)}"
            elif winner_id == p2_id:
                h2h_p2_wins += 1
                label = f"✅ {player2.get('name', p2)}"
            else:
                label = "?"
            if len(h2h_recent) < 3:
                h2h_recent.append(f"{label} — {tournament} {score_raw}".strip())
        except Exception:
            continue

    # 5. Forme récente
    p1_results = _extract_recent_results(p1_res_raw, 5)
    p2_results = _extract_recent_results(p2_res_raw, 5)

    # 6. Rankings
    p1_rank = player1.get("rankings", [{}])[0].get("rank") if player1.get("rankings") else player1.get("ranking")
    p2_rank = player2.get("rankings", [{}])[0].get("rank") if player2.get("rankings") else player2.get("ranking")

    # 7. Cotes
    odds_info = {}
    if odds_match:
        books = {b["key"]: b for b in odds_match.get("bookmakers", [])}
        pin = books.get("pinnacle")
        if pin:
            for mkt in pin["markets"]:
                if mkt["key"] == "h2h":
                    total = sum(1 / o["price"] for o in mkt["outcomes"] if o["price"] > 1)
                    if total:
                        for o in mkt["outcomes"]:
                            prob = round((1 / o["price"]) / total * 100, 1)
                            odds_info[o["name"]] = {"true_prob": prob, "pinnacle_odds": round(o["price"], 2)}
        for bkey, book in books.items():
            if bkey == "pinnacle":
                continue
            for mkt in book["markets"]:
                if mkt["key"] != "h2h":
                    continue
                for o in mkt["outcomes"]:
                    if o["name"] in odds_info:
                        cur_best = odds_info[o["name"]].get("best_odds", 0)
                        if o["price"] > cur_best:
                            odds_info[o["name"]]["best_odds"] = round(o["price"], 2)
                            odds_info[o["name"]]["best_book"] = book["title"]

    return {
        "sport": "tennis",
        "player1": {"name": player1.get("name", p1), "rank": p1_rank, "country": player1.get("country_code", "?")},
        "player2": {"name": player2.get("name", p2), "rank": p2_rank, "country": player2.get("country_code", "?")},
        "h2h_total": h2h_p1_wins + h2h_p2_wins,
        "h2h_p1_wins": h2h_p1_wins,
        "h2h_p2_wins": h2h_p2_wins,
        "h2h_recent": h2h_recent,
        "p1_form": p1_results,
        "p2_form": p2_results,
        "odds": odds_info,
    }
