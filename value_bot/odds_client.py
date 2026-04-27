"""Client The Odds API — fetch et analyse des value bets."""

import httpx
import logging
from datetime import datetime, timezone, timedelta
from config import ODDS_API_KEYS, SOFT_BOOKS, MIN_EDGE

logger = logging.getLogger(__name__)
BASE_URL = "https://api.the-odds-api.com/v4"

_remaining: dict[str, int] = {}  # quota restant par clé
_key_index = 0                   # clé active


def _active_key() -> str | None:
    """Retourne la première clé avec du quota restant."""
    global _key_index
    for i in range(len(ODDS_API_KEYS)):
        idx = (_key_index + i) % len(ODDS_API_KEYS)
        key = ODDS_API_KEYS[idx]
        rem = _remaining.get(key)
        if rem is None or rem > 5:
            _key_index = idx
            return key
    return None


async def _fetch(sport: str, markets: str = "h2h,totals") -> list:
    if not ODDS_API_KEYS:
        logger.error("Aucune ODDS_API_KEY configurée dans .env")
        return []

    key = _active_key()
    if not key:
        logger.warning("Toutes les clés Odds API sont épuisées")
        return []

    params = {
        "apiKey":     key,
        "regions":    "eu,uk",
        "markets":    markets,
        "oddsFormat": "decimal",
        "bookmakers": "pinnacle," + ",".join(SOFT_BOOKS),
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{BASE_URL}/sports/{sport}/odds", params=params)
        rem = int(r.headers.get("x-requests-remaining", -1))
        _remaining[key] = rem
        if rem <= 5:
            logger.warning("Clé %s...%s épuisée (%d restants), bascule sur la suivante", key[:8], key[-4:], rem)
            _key_index = (ODDS_API_KEYS.index(key) + 1) % len(ODDS_API_KEYS)
        if r.status_code == 200:
            logger.debug("Odds API [%s] OK — %d req restantes (clé %s…)", sport, rem, key[:8])
            return r.json()
        elif r.status_code == 401:
            logger.error("Odds API 401 — clé invalide: %s…", key[:8])
        elif r.status_code == 422:
            pass
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


def _dedup(vbs: list) -> list:
    """Garde le meilleur edge par (match + marché)."""
    seen, unique = set(), []
    for vb in sorted(vbs, key=lambda x: x["edge"], reverse=True):
        key = (vb["home"], vb["away"], vb["market"])
        if key not in seen:
            seen.add(key)
            unique.append(vb)
    return unique


async def fetch_value_bets(sports: list, hours_ahead: int = 36, min_edge: float = MIN_EDGE) -> list:
    """Fetch et analyse les value bets sur la liste de sports donnée."""
    now    = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours_ahead)
    all_vbs = []

    for sport in sports:
        for match in await _fetch(sport):
            try:
                ko = datetime.fromisoformat(match["commence_time"].replace("Z", "+00:00"))
                if ko < now or ko > cutoff:
                    continue
                all_vbs.extend(_analyze(match, min_edge))
            except Exception as e:
                logger.error("Parse error [%s]: %s", sport, e)

    unique = _dedup(all_vbs)
    logger.info("Value bets trouvés : %d (edge ≥ %.0f%%)", len(unique), min_edge * 100)
    return unique


async def fetch_schedule_and_bets(sports: list, hours_ahead: int = 36, min_edge: float = MIN_EDGE) -> dict:
    """
    Fetch unique du matin : retourne les value bets ET le planning des matchs
    pour programmer les checks ciblés (KO-5min, MT).
    """
    now    = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours_ahead)
    all_vbs, schedule = [], []
    seen_matches = set()

    for sport in sports:
        for match in await _fetch(sport):
            try:
                ko = datetime.fromisoformat(match["commence_time"].replace("Z", "+00:00"))
                if ko < now or ko > cutoff:
                    continue
                all_vbs.extend(_analyze(match, min_edge))
                key = (match["home_team"], match["away_team"])
                if key not in seen_matches:
                    seen_matches.add(key)
                    schedule.append({
                        "sport":   sport,
                        "home":    match["home_team"],
                        "away":    match["away_team"],
                        "kickoff": ko,
                    })
            except Exception as e:
                logger.error("Parse error [%s]: %s", sport, e)

    return {"bets": _dedup(all_vbs), "schedule": schedule}


async def fetch_sport_value_bets(sport: str, min_edge: float = MIN_EDGE) -> list:
    """Check ciblé sur un seul sport (utilisé pour KO-5min et MT)."""
    now = datetime.now(timezone.utc)
    all_vbs = []
    for match in await _fetch(sport):
        try:
            ko = datetime.fromisoformat(match["commence_time"].replace("Z", "+00:00"))
            # Uniquement les matchs qui commencent dans les 3 prochaines heures
            if not (now - timedelta(hours=2) <= ko <= now + timedelta(hours=3)):
                continue
            all_vbs.extend(_analyze(match, min_edge))
        except Exception as e:
            logger.error("Parse error ciblé [%s]: %s", sport, e)
    return _dedup(all_vbs)


async def fetch_scores(sports: list) -> list:
    """Fetch les résultats des matchs terminés aujourd'hui."""
    if not ODDS_API_KEYS:
        return []
    all_scores = []
    for sport in sports:
        key = _active_key()
        if not key:
            break
        try:
            params = {"apiKey": key, "daysFrom": 1, "dateFormat": "iso"}
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(f"{BASE_URL}/sports/{sport}/scores", params=params)
            if r.headers.get("x-requests-remaining"):
                _remaining[key] = int(r.headers["x-requests-remaining"])
            if r.status_code == 200:
                all_scores.extend(r.json())
        except Exception as e:
            logger.error("Scores fetch error [%s]: %s", sport, e)
    return all_scores


def quota_remaining() -> dict:
    """Retourne le quota restant par clé."""
    return {f"clé {i+1} ({k[:8]}…)": _remaining.get(k, 500) for i, k in enumerate(ODDS_API_KEYS)}
