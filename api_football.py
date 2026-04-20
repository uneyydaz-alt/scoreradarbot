"""Client pour l'API-Football (api-sports.io)."""

import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from config import API_FOOTBALL_BASE_URL, API_FOOTBALL_KEY, POPULAR_LEAGUES

logger = logging.getLogger(__name__)

# Cache des cotes live (rafraîchi toutes les 5 min)
_live_odds_cache = {
    "data": {},     # {fixture_id: {over_line: odd_value}}
    "timestamp": 0,
}
LIVE_ODDS_CACHE_TTL = 300  # 5 minutes

HEADERS = {
    "x-apisports-key": API_FOOTBALL_KEY,
}


async def _get(endpoint: str, params: Optional[Dict[str, Any]] = None) -> dict:
    """Requête GET générique vers l'API-Football."""
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{API_FOOTBALL_BASE_URL}/{endpoint}",
            headers=HEADERS,
            params=params or {},
        )
        response.raise_for_status()
        data = response.json()

        # Vérifier les erreurs API
        errors = data.get("errors")
        if errors:
            logger.error("API-Football errors: %s", errors)
            return {"response": []}

        return data


async def get_live_fixtures(league_ids: Optional[List[int]] = None) -> List[dict]:
    """Récupère tous les matchs en direct.

    Si league_ids est fourni, filtre localement par ces ligues.
    """
    data = await _get("fixtures", {"live": "all"})
    fixtures = data.get("response", [])
    logger.info("Matchs en direct (total): %d", len(fixtures))

    if league_ids:
        fixtures = [
            f for f in fixtures
            if f.get("league", {}).get("id") in league_ids
        ]
        logger.info("Matchs après filtre ligues: %d", len(fixtures))

    return fixtures


async def get_fixture_by_id(fixture_id: int) -> dict:
    """Recupere un match par son ID (live ou termine)."""
    data = await _get("fixtures", {"id": fixture_id})
    fixtures = data.get("response", [])
    return fixtures[0] if fixtures else {}


async def get_fixture_statistics(fixture_id: int) -> List[dict]:
    """Récupère les statistiques d'un match en direct."""
    data = await _get("fixtures/statistics", {"fixture": fixture_id})
    return data.get("response", [])


async def get_fixture_events(fixture_id: int) -> List[dict]:
    """Récupère les événements d'un match (buts, cartons, etc.)."""
    data = await _get("fixtures/events", {"fixture": fixture_id})
    return data.get("response", [])


def parse_fixture_info(fixture: dict) -> dict:
    """Extrait les infos clés d'un match depuis la réponse API."""
    fixture_data = fixture.get("fixture", {})
    league_data = fixture.get("league", {})
    teams = fixture.get("teams", {})
    goals = fixture.get("goals", {})
    status = fixture_data.get("status", {})

    return {
        "fixture_id": fixture_data.get("id"),
        "league_id": league_data.get("id"),
        "league_name": POPULAR_LEAGUES.get(league_data.get("id"), league_data.get("name", "Inconnu")),
        "league_country": league_data.get("country", ""),
        "home_team": teams.get("home", {}).get("name", "Inconnu"),
        "away_team": teams.get("away", {}).get("name", "Inconnu"),
        "home_goals": goals.get("home", 0) or 0,
        "away_goals": goals.get("away", 0) or 0,
        "elapsed": status.get("elapsed", 0) or 0,
        "status_short": status.get("short", ""),
        "events": fixture.get("events", []),
    }


async def get_live_odds(fixture_id: int, over_line: float) -> float:
    """Récupère la cote live Over pour un match et une ligne donnée.

    Args:
        fixture_id: ID du match
        over_line: ligne Over (ex: 0.5, 1.5, 2.5, 3.5, 4.5)

    Returns:
        La cote Over, ou 0.0 si pas trouvée.
    """
    now = time.time()

    # Utiliser le cache si frais
    if (now - _live_odds_cache["timestamp"]) < LIVE_ODDS_CACHE_TTL and _live_odds_cache["data"]:
        fixture_odds = _live_odds_cache["data"].get(fixture_id, {})
        odds_val = fixture_odds.get(over_line, 0.0)
        if odds_val:
            return odds_val

    # Rafraîchir le cache complet
    try:
        data = await _get("odds/live")
        all_matches = data.get("response", [])
        new_cache = {}

        for match in all_matches:
            fid = match.get("fixture", {}).get("id")
            if not fid:
                continue
            odds_dict = {}
            for odds_group in match.get("odds", []):
                name = odds_group.get("name", "")
                # "Over/Under" = full match, skip "1st Half" etc.
                if name == "Over/Under" or name == "Over/Under Line":
                    for val in odds_group.get("values", []):
                        if val.get("value") == "Over":
                            handicap = val.get("handicap")
                            if handicap is not None:
                                try:
                                    h = float(handicap)
                                    odd = float(val.get("odd", 0))
                                    if odd > 0:
                                        odds_dict[h] = odd
                                except (ValueError, TypeError):
                                    pass
            if odds_dict:
                new_cache[fid] = odds_dict

        _live_odds_cache["data"] = new_cache
        _live_odds_cache["timestamp"] = now
        logger.info("Cotes live chargées: %d matchs", len(new_cache))

        return new_cache.get(fixture_id, {}).get(over_line, 0.0)

    except Exception as e:
        logger.error("Erreur cotes live: %s", e)
        return 0.0


def parse_statistics(stats_response: List[dict]) -> dict:
    """Parse les statistiques d'un match en un dict utilisable.

    Retourne un dict avec les stats de chaque équipe :
    {
        "home": {"Shots on Goal": 5, "Ball Possession": "65%", ...},
        "away": {"Shots on Goal": 3, "Ball Possession": "35%", ...},
    }
    """
    result = {"home": {}, "away": {}}

    for i, team_stats in enumerate(stats_response):
        side = "home" if i == 0 else "away"
        for stat in team_stats.get("statistics", []):
            stat_type = stat.get("type", "")
            value = stat.get("value")
            result[side][stat_type] = value

    return result
