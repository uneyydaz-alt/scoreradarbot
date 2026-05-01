"""Détecteur de value bets pré-match.

Flux :
  1. Toutes les N minutes, récupère les matchs à venir (statut NS).
  2. Pour chaque match, récupère les cotes 1X2.
  3. Première détection → enregistre les cotes initiales (pas de tweet encore).
  4. Scan suivant → si les cotes ont chuté d'au moins MIN_DROP_ABS ou MIN_DROP_PCT
     depuis l'enregistrement initial, génère une action "drop".
  5. L'appelant (bot.py) poste le tweet via build_value_tweet().
"""

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx

from config import API_FOOTBALL_KEY, API_FOOTBALL_BASE_URL

logger = logging.getLogger(__name__)

VALUE_STATE_FILE = Path(__file__).parent / "value_state.json"

# --- Seuils ---
MIN_ODDS = 1.40       # cote minimale pour surveiller
MAX_ODDS = 3.50       # cote maximale pour surveiller
MIN_DROP_ABS = 0.08   # chute absolue déclenchant l'alerte
MIN_DROP_PCT = 0.04   # chute relative déclenchant l'alerte (4 %)
HOURS_AHEAD = 8       # horizon de surveillance (heures avant le coup d'envoi)

# --- Caches ---
_fixtures_cache: dict = {"data": [], "timestamp": 0.0}
FIXTURES_CACHE_TTL = 1800  # 30 min

_odds_cache: dict = {}     # {fixture_id: {"data": dict, "ts": float}}
ODDS_CACHE_TTL = 300       # 5 min


# ── État persistant ──────────────────────────────────────────────────────────

def _load_state() -> dict:
    if not VALUE_STATE_FILE.exists():
        return {}
    try:
        with open(VALUE_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        with open(VALUE_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("Erreur sauvegarde value_state: %s", e)


# ── Appel API ────────────────────────────────────────────────────────────────

async def _api_get(endpoint: str, params: dict) -> dict:
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{API_FOOTBALL_BASE_URL}/{endpoint}",
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("errors"):
            logger.error("API-Football errors: %s", data["errors"])
            return {"response": []}
        return data


# ── Récupération des matchs ──────────────────────────────────────────────────

async def get_upcoming_fixtures() -> list:
    """Retourne les matchs non commencés dans les prochaines HOURS_AHEAD heures."""
    now = time.time()
    if now - _fixtures_cache["timestamp"] < FIXTURES_CACHE_TTL and _fixtures_cache["data"]:
        return _fixtures_cache["data"]

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        data = await _api_get("fixtures", {"date": date_str, "status": "NS"})
        fixtures = data.get("response", [])
        cutoff_ts = (datetime.now(timezone.utc) + timedelta(hours=HOURS_AHEAD)).timestamp()

        upcoming = [
            f for f in fixtures
            if now <= f.get("fixture", {}).get("timestamp", 0) <= cutoff_ts
        ]
        _fixtures_cache["data"] = upcoming
        _fixtures_cache["timestamp"] = now
        logger.info("Fixtures à venir: %d (horizon %dh)", len(upcoming), HOURS_AHEAD)
        return upcoming
    except Exception as e:
        logger.error("Erreur get_upcoming_fixtures: %s", e)
        return []


# ── Récupération des cotes ───────────────────────────────────────────────────

async def get_fixture_odds(fixture_id: int) -> dict:
    """Retourne les cotes 1X2 d'un match : {home, draw, away} ou {}."""
    now = time.time()
    cached = _odds_cache.get(fixture_id)
    if cached and now - cached["ts"] < ODDS_CACHE_TTL:
        return cached["data"]

    try:
        data = await _api_get("odds", {"fixture": fixture_id, "bet": 1})
        for entry in data.get("response", []):
            for bookmaker in entry.get("bookmakers", []):
                for bet in bookmaker.get("bets", []):
                    if bet.get("name") == "Match Winner":
                        vals = {
                            v["value"]: float(v["odd"])
                            for v in bet.get("values", [])
                            if "odd" in v and "value" in v
                        }
                        home = vals.get("Home", 0.0)
                        draw = vals.get("Draw", 0.0)
                        away = vals.get("Away", 0.0)
                        if home and away:
                            result = {"home": home, "draw": draw, "away": away}
                            _odds_cache[fixture_id] = {"data": result, "ts": now}
                            return result

        _odds_cache[fixture_id] = {"data": {}, "ts": now}
        return {}
    except Exception as e:
        logger.error("Erreur cotes fixture %d: %s", fixture_id, e)
        return {}


# ── Détection de value ───────────────────────────────────────────────────────

def find_value_pick(odds: dict) -> Optional[dict]:
    """Identifie le pick de value dans les cotes 1X2.

    Retourne {"side": "home"|"away", "odds": float} si le favori a des cotes
    dans [MIN_ODDS, MAX_ODDS], sinon None.
    """
    home = odds.get("home", 0.0)
    away = odds.get("away", 0.0)
    if not home or not away:
        return None

    if home <= away:
        fav_side, fav_odds = "home", home
    else:
        fav_side, fav_odds = "away", away

    if MIN_ODDS <= fav_odds <= MAX_ODDS:
        return {"side": fav_side, "odds": fav_odds}
    return None


# ── Scan principal ───────────────────────────────────────────────────────────

async def check_value_bets() -> list:
    """Scanne les matchs à venir et détecte les drops de cotes.

    Retourne une liste d'actions à poster :
    [{"type": "drop", "home": str, "away": str, "country": str,
      "team": str, "initial_odds": float, "current_odds": float,
      "kickoff": str, "state_key": str}]
    """
    if not API_FOOTBALL_KEY:
        return []

    fixtures = await get_upcoming_fixtures()
    state = _load_state()
    actions = []
    now = time.time()

    # Purger les entrées correspondant à des matchs passés depuis > 24 h
    state = {k: v for k, v in state.items() if v.get("kickoff_ts", now) > now - 86400}

    for fixture in fixtures:
        fix_data = fixture.get("fixture", {})
        league_data = fixture.get("league", {})
        teams = fixture.get("teams", {})

        fixture_id = fix_data.get("id")
        if not fixture_id:
            continue

        country = league_data.get("country", "")
        league_name = league_data.get("name", "")
        home_team = teams.get("home", {}).get("name", "")
        away_team = teams.get("away", {}).get("name", "")
        kickoff_ts = fix_data.get("timestamp", 0)
        kickoff_str = (
            datetime.fromtimestamp(kickoff_ts, tz=timezone.utc).strftime("%H:%M")
            if kickoff_ts else "?"
        )

        odds = await get_fixture_odds(fixture_id)
        pick = find_value_pick(odds)
        if not pick:
            continue

        team_name = home_team if pick["side"] == "home" else away_team
        current_odds = pick["odds"]
        state_key = f"{fixture_id}_{pick['side']}"

        if state_key not in state:
            # Première détection : enregistrer sans poster (on attend le drop)
            state[state_key] = {
                "fixture_id": fixture_id,
                "home": home_team,
                "away": away_team,
                "country": country,
                "league": league_name,
                "team": team_name,
                "side": pick["side"],
                "initial_odds": current_odds,
                "last_odds": current_odds,
                "kickoff_ts": kickoff_ts,
                "kickoff": kickoff_str,
                "alerted": False,
                "detected_at": now,
            }
            logger.info(
                "Value enregistrée: %s @ %.2f (%s vs %s)",
                team_name, current_odds, home_team, away_team,
            )
        else:
            entry = state[state_key]
            initial_odds = entry["initial_odds"]
            drop_abs = initial_odds - current_odds
            drop_pct = drop_abs / initial_odds if initial_odds else 0

            if (
                not entry.get("alerted")
                and current_odds < initial_odds
                and (drop_abs >= MIN_DROP_ABS or drop_pct >= MIN_DROP_PCT)
            ):
                actions.append({
                    "type": "drop",
                    "state_key": state_key,
                    "fixture_id": fixture_id,
                    "home": home_team,
                    "away": away_team,
                    "country": country,
                    "league": league_name,
                    "team": team_name,
                    "side": pick["side"],
                    "initial_odds": initial_odds,
                    "current_odds": current_odds,
                    "kickoff": kickoff_str,
                })
                state[state_key]["alerted"] = True
                logger.info(
                    "Drop alerté: %s %.2f → %.2f (%s vs %s)",
                    team_name, initial_odds, current_odds, home_team, away_team,
                )

            state[state_key]["last_odds"] = current_odds

    _save_state(state)
    return actions
