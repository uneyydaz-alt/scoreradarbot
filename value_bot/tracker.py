"""Suivi des alertes déjà envoyées — évite les doublons dans la journée."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)
SENT_FILE   = Path(__file__).parent / "sent_alerts.json"
DIGEST_FILE = Path(__file__).parent / "digest_state.json"


def _load() -> dict:
    try:
        if SENT_FILE.exists():
            return json.loads(SENT_FILE.read_text())
    except Exception:
        pass
    return {}


def _save(data: dict):
    try:
        SENT_FILE.write_text(json.dumps(data))
    except Exception as e:
        logger.error("Tracker save error: %s", e)


def already_sent(vb_id: str) -> bool:
    """Retourne True si ce value bet a déjà été envoyé aujourd'hui."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    data  = _load()
    return data.get(vb_id) == today


def mark_sent(vb_id: str):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    data  = _load()
    data[vb_id] = today
    # Purge des entrées d'hier
    data = {k: v for k, v in data.items() if v == today}
    _save(data)


def filter_new(vbs: list) -> list:
    """Filtre la liste pour ne garder que les value bets pas encore envoyés."""
    return [vb for vb in vbs if not already_sent(vb["id"])]


def mark_all_sent(vbs: list):
    for vb in vbs:
        mark_sent(vb["id"])


def save_digest(message_id: int, chat_id, bets: list):
    """Sauvegarde le message_id du digest matin + les paris pour validation soir."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        DIGEST_FILE.write_text(json.dumps({
            "date":       today,
            "message_id": message_id,
            "chat_id":    str(chat_id),
            "bets":       bets,
        }, ensure_ascii=False))
    except Exception as e:
        logger.error("Digest state save error: %s", e)


def load_digest() -> dict | None:
    """Charge l'état du digest si c'est bien celui d'aujourd'hui."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        if DIGEST_FILE.exists():
            data = json.loads(DIGEST_FILE.read_text())
            if data.get("date") == today:
                return data
    except Exception:
        pass
    return None
