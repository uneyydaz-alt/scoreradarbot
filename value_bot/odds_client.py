"""Client The Odds API — fetch et analyse des value bets."""

import httpx
import logging
from datetime import datetime, timezone, timedelta
from config import ODDS_API_KEY, SOFT_BOOKS, MIN_EDGE

logger = logging.getLogger(__name__)
BASE_URL = "https://api.the-odds-api.com/v4"

_requests_remaining = None  # suivi du quota


async def _fetch(sport: str, markets: str = "h2h,totals") -> list:
    global _requests_remaining
    if not ODDS_API_KEY:
        logger.error("ODDS_API_KEY manquant dans .env")
        return []
    if _requests_remaining is not None and _requests_remaining <= 5:
        logger.warning("Quota Odds API presque épuisé (%d restants) — fetch ignoré", _requests_remaining)
        return []

    params = {
        "apiKey":      ODDS_API_KEY,
        "regions":     "eu,uk",
        "markets":     markets,
        "oddsFormat":  "decimal",
        "bookmakers":  "pinnacle," + ",".join(SOFT_BOOKS),
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{BASE_URL}/sports/{sport}/odds", params=params)
        _requests_remaining = int(r.headers.get("x-requests-remaining", -1))
        if r.status_code == 200:
            logger.debug("Odds API [%s] OK — %d req restantes", sport, _requests_remaining)
            return r.json()
        elif r.status_code == 401:
            logger.error("Odds API 401 — clé invalide")
        elif r.status_code == 422:
            pass  # pas de matchs pour ce sport, normal
        else:
            logger.error("Odds API [%s] HTTP %d", sport, r.status_code)
    except Exception as e:
        logger.error("Odds API fetch error [%s]: %s", sport, e)
    return []


def _true_probs(outcomes: list) -> dict:
    """Retire la marge Pinnacle → probabilités réelles par outcome."""
    total = sum(1 / o["price"] for o in outcomes if o["price"] > 1)
    if not total:
        return {}
    return {o["name"]: (1 / o["price"]) / total for o in outcomes}


def _analyze(match: dict, min_edge: float = MIN_EDGE) -> list:
    """Retourne les value bets d'un match (comparaison soft books vs Pinnacle)."""
    books = {b["key"]: b for b in match.get("bookmakers", [])}
    pinnacle = books.get("pinnacle")
    if not pinnacle:
        return []

    ref = {}
    for mkt in pinnacle["markets"]:
        ref[mkt["key"]] = _true_probs(mkt["outcomes"])

    found = []
    for bkey, book in books.items():
        if bkey == "pinnacle":
            continue
        for mkt in book["markets"]:
            mkey = mkt["key"]
            if mkey not in ref:
                continue
            for outcome in mkt["outcomes"]:
                name      = outcome["name"]
                soft_odds = outcome["price"]
                true_p    = ref[mkey].get(name)
                if not true_p or soft_odds <= 1:
                    continue
                edge = true_p * soft_odds - 1
                if edge < min_edge:
                    continue

                fair = 1 / true_p
                if mkey == "h2h":
                    label = f"1X2 — {name}"
                elif mkey == "totals":
                    pt = outcome.get("point", "")
                    label = f"{'Over' if name == 'Over' else 'Under'} {pt}"
                else:
                    label = f"{mkey} — {name}"

                found.append({
                    "id":           f"{match['id']}_{mkey}_{name}",
                    "home":         match["home_team"],
                    "away":         match["away_team"],
                    "league":       match.get("sport_title", ""),
                    "kickoff":      match.get("commence_time", ""),
                    "market":       label,
                    "bookmaker":    book["title"],
                    "soft_odds":    round(soft_odds, 2),
                    "fair_odds":    round(fair, 2),
                    "implied_prob": round(100 / soft_odds, 2),
                    "true_prob":    round(true_p * 100, 2),
                    "edge":         round(edge * 100, 2),
                    "odds_low":     round(fair * 0.96, 2),
                    "odds_high":    round(fair * 1.06, 2),
                })

    return sorted(found, key=lambda x: x["edge"], reverse=True)


async def fetch_value_bets(sports: list, hours_ahead: int = 36, min_edge: float = MIN_EDGE) -> list:
    """Fetch et analyse les value bets sur la liste de sports donnée."""
    now    = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours_ahead)
    all_vbs = []

    for sport in sports:
        matches = await _fetch(sport)
        for match in matches:
            try:
                ko = datetime.fromisoformat(match["commence_time"].replace("Z", "+00:00"))
                if ko < now or ko > cutoff:
                    continue
                all_vbs.extend(_analyze(match, min_edge))
            except Exception as e:
                logger.error("Parse error [%s]: %s", sport, e)

    # Déduplique : garde le meilleur edge par (match + marché)
    seen, unique = set(), []
    for vb in sorted(all_vbs, key=lambda x: x["edge"], reverse=True):
        key = (vb["home"], vb["away"], vb["market"])
        if key not in seen:
            seen.add(key)
            unique.append(vb)

    logger.info("Value bets trouvés : %d (edge ≥ %.0f%%)", len(unique), min_edge * 100)
    return unique


def quota_remaining() -> int | None:
    return _requests_remaining
