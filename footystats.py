"""Client pour l'API FootyStats (football-data-api.com)."""

import logging
import time
import json
from pathlib import Path
import unicodedata
from typing import Any, Dict, List, Optional

import httpx

from config import FOOTYSTATS_BASE_URL, FOOTYSTATS_API_KEY

logger = logging.getLogger(__name__)

# Cache ACCUMULATIF des matchs du jour
# FootyStats retire les matchs en cours de todays-matches,
# donc on accumule pour ne jamais perdre les données pré-match.
_cache: Dict[str, Any] = {
    "matches_by_id": {},
    "timestamp": 0,
    "day": "",
}
CACHE_TTL = 900  # 15 minutes entre chaque refresh
CACHE_FILE = Path(__file__).parent / "footystats_cache.json"


def _load_cache_from_disk():
    """Charge le cache FootyStats depuis le disque."""
    import datetime
    today = datetime.date.today().isoformat()
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if saved.get("day") == today:
                _cache["matches_by_id"] = saved.get("matches_by_id", {})
                _cache["day"] = today
                _cache["timestamp"] = saved.get("timestamp", 0)
                logger.info("FootyStats cache chargé depuis disque: %d matchs", len(_cache["matches_by_id"]))
                return
        except Exception as e:
            logger.error("Erreur lecture cache FootyStats: %s", e)
    _cache["matches_by_id"] = {}
    _cache["day"] = today
    _cache["timestamp"] = 0


def _save_cache_to_disk():
    """Sauvegarde le cache FootyStats sur disque."""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "day": _cache["day"],
                "timestamp": _cache["timestamp"],
                "matches_by_id": _cache["matches_by_id"],
            }, f)
    except Exception as e:
        logger.error("Erreur sauvegarde cache FootyStats: %s", e)


# Charger le cache au démarrage
_load_cache_from_disk()


async def _get(endpoint: str, params: Optional[Dict[str, Any]] = None) -> dict:
    """Requête GET vers l'API FootyStats."""
    if not FOOTYSTATS_API_KEY:
        return {"data": []}

    all_params = {"key": FOOTYSTATS_API_KEY}
    if params:
        all_params.update(params)

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{FOOTYSTATS_BASE_URL}/{endpoint}",
            params=all_params,
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("success", True):
            logger.error("FootyStats erreur: %s", data)
            return {"data": []}

        return data


async def get_todays_matches() -> List[dict]:
    """Récupère les matchs du jour avec cache accumulatif.

    Accumule les matchs car FootyStats retire les matchs en cours.
    Reset à minuit (nouveau jour).
    """
    import datetime
    now = time.time()
    today = datetime.date.today().isoformat()

    # Reset le cache si nouveau jour
    if _cache["day"] != today:
        _cache["matches_by_id"] = {}
        _cache["day"] = today
        _cache["timestamp"] = 0

    # Re-fetch si cache expiré
    if (now - _cache["timestamp"]) >= CACHE_TTL:
        try:
            data = await _get("todays-matches")
            matches = data.get("data", [])
            new_count = 0
            for m in matches:
                key = "%s_%s_%s" % (
                    m.get("competition_id", 0),
                    _normalize(m.get("home_name", "")),
                    _normalize(m.get("away_name", "")),
                )
                if key not in _cache["matches_by_id"]:
                    _cache["matches_by_id"][key] = m
                    new_count += 1
            _cache["timestamp"] = now
            total = len(_cache["matches_by_id"])
            logger.info("FootyStats: %d matchs en cache, %d nouveaux", total, new_count)
            _save_cache_to_disk()
        except Exception as e:
            logger.error("FootyStats erreur: %s", e)

    return list(_cache["matches_by_id"].values())


# Alias pour les noms qui diffèrent totalement entre APIs
_ALIASES = {
    "copenhagen": "kobenhavn",
    "fc copenhagen": "kobenhavn",
    "sonderjyske": "sonderjyske",
    "randers fc": "randers",
    "aarhus": "agf",
    "brann": "sk brann",
}


def _normalize(name: str) -> str:
    """Normalise un nom d'équipe pour le matching."""
    # Caractères spéciaux non décomposés par NFKD
    special = {"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "ð": "d", "Ð": "D",
               "ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "ß": "ss"}
    for char, repl in special.items():
        name = name.replace(char, repl)
    # Retirer les accents
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    # Lowercase + retirer ponctuation
    name = name.lower().strip()
    # Abréviations courantes
    name = name.replace(" utd", " united")
    # Retirer suffixes courants
    for suffix in (" fc", " cf", " sc", " ac", " fk", " sk", " 1893", " 1907", " 1908"):
        if name.endswith(suffix):
            name = name[:-len(suffix)].strip()
    # Retirer prefixes courants
    if name.startswith("fc "):
        name = name[3:]
    return name


def _apply_alias(name: str) -> str:
    """Applique les alias connus."""
    return _ALIASES.get(name, name)


def find_match_data(home_team: str, away_team: str, matches: List[dict]) -> Optional[dict]:
    """Cherche un match FootyStats correspondant aux noms d'équipes API-Football.

    Utilise un matching flou car les noms diffèrent entre les 2 APIs.
    """
    home_norm = _apply_alias(_normalize(home_team))
    away_norm = _apply_alias(_normalize(away_team))

    for match in matches:
        fs_home = _apply_alias(_normalize(match.get("home_name", "")))
        fs_away = _apply_alias(_normalize(match.get("away_name", "")))

        # Match exact après normalisation
        if fs_home == home_norm and fs_away == away_norm:
            return match

        # Match par inclusion (un nom contient l'autre)
        if (_fuzzy_match(home_norm, fs_home) and _fuzzy_match(away_norm, fs_away)):
            return match

    return None


# Mots non-significatifs pour le matching
_STOP_WORDS = {
    "fc", "cf", "sc", "ac", "fk", "sk", "nk", "bk", "if", "sv", "vfl",
    "fsv", "tsv", "1fc", "rb", "us", "as", "ss", "cd", "ud", "rc",
    "de", "da", "do", "dos", "di", "del", "la", "le", "les", "el",
    "al", "the", "and", "et", "van", "von", "den", "der",
    "club", "united", "city", "town", "real", "sporting", "atletico",
    "athletic", "dynamo", "olympique", "racing",
    "b", "ii", "1893", "1907", "1908", "1899", "1932",
}


def _significant_words(name: str) -> set:
    """Extrait les mots significatifs (>= 3 lettres, pas stop words)."""
    words = set()
    for w in name.replace("-", " ").replace(".", " ").split():
        w = w.strip()
        if w and w not in _STOP_WORDS and len(w) >= 3:
            words.add(w)
    return words


def _fuzzy_match(name_a: str, name_b: str) -> bool:
    """Vérifie si deux noms d equipes correspondent (matching intelligent)."""
    if not name_a or not name_b:
        return False
    # Match exact
    if name_a == name_b:
        return True
    # L un contient l autre
    if name_a in name_b or name_b in name_a:
        return True

    # Matching par mots significatifs
    words_a = _significant_words(name_a)
    words_b = _significant_words(name_b)

    if not words_a or not words_b:
        return False

    # Si un mot significatif de A (>= 4 lettres) est dans B ou vice versa
    for w in words_a:
        if len(w) >= 4 and (w in name_b or any(w in wb or wb in w for wb in words_b)):
            return True
    for w in words_b:
        if len(w) >= 4 and (w in name_a or any(w in wa or wa in w for wa in words_a)):
            return True

    # Ratio de mots en commun (Jaccard)
    common = words_a & words_b
    if common:
        ratio = len(common) / min(len(words_a), len(words_b))
        if ratio >= 0.5:
            return True

    return False


def parse_prematch_data(match: dict) -> dict:
    """Extrait les données pré-match utiles d'un match FootyStats."""
    return {
        "btts_potential": _safe_float(match.get("btts_potential")),
        "o15_potential": _safe_float(match.get("o15_potential")),
        "o25_potential": _safe_float(match.get("o25_potential")),
        "o35_potential": _safe_float(match.get("o35_potential")),
        "avg_potential": _safe_float(match.get("avg_potential")),
        # Cotes par Over (Over 0.5 à Over 4.5)
        "odds_ft_over05": _safe_float(match.get("odds_ft_over05")),
        "odds_ft_over15": _safe_float(match.get("odds_ft_over15")),
        "odds_ft_over25": _safe_float(match.get("odds_ft_over25")),
        "odds_ft_over35": _safe_float(match.get("odds_ft_over35")),
        "odds_ft_over45": _safe_float(match.get("odds_ft_over45")),
        "odds_btts_yes": _safe_float(match.get("odds_btts_yes")),
        "home_ppg": _safe_float(match.get("home_ppg")),
        "away_ppg": _safe_float(match.get("away_ppg")),
    }


def _safe_float(value) -> float:
    """Convertit en float, retourne 0.0 si impossible."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0
