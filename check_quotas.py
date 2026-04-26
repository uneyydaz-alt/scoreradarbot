"""Vérifie les quotas des 3 APIs utilisées par le projet."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import httpx
from dotenv import load_dotenv
load_dotenv()

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")
FOOTYSTATS_API_KEY = os.getenv("FOOTYSTATS_API_KEY", "")
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")


def check_api_football():
    if not API_FOOTBALL_KEY:
        return "❌ Clé manquante (API_FOOTBALL_KEY)"
    try:
        r = httpx.get(
            "https://v3.football.api-sports.io/status",
            headers={"x-apisports-key": API_FOOTBALL_KEY},
            timeout=10,
        )
        d = r.json().get("response", {})
        sub = d.get("subscription", {})
        req = d.get("requests", {})
        plan = sub.get("plan", "?")
        used = req.get("current", "?")
        limit = req.get("limit_day", "?")
        remaining = (limit - used) if isinstance(limit, int) and isinstance(used, int) else "?"
        return f"✅ Plan: {plan} | Utilisées: {used}/{limit} aujourd'hui | Restantes: {remaining}"
    except Exception as e:
        return f"❌ Erreur: {e}"


def check_footystats():
    if not FOOTYSTATS_API_KEY:
        return "❌ Clé manquante (FOOTYSTATS_API_KEY)"
    try:
        r = httpx.get(
            "https://api.football-data-api.com/league-list",
            params={"key": FOOTYSTATS_API_KEY},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            credits = data.get("credits_remaining") or data.get("metadata", {}).get("credits_remaining")
            if credits is not None:
                return f"✅ Crédits restants: {credits}"
            return "✅ API accessible (pas d'info quota dans la réponse)"
        elif r.status_code == 401:
            return "❌ 401 — Clé invalide"
        else:
            return f"❌ HTTP {r.status_code}"
    except Exception as e:
        return f"❌ Erreur: {e}"


def check_odds_api():
    if not ODDS_API_KEY:
        return "❌ Clé manquante (ODDS_API_KEY)"
    try:
        r = httpx.get(
            "https://api.the-odds-api.com/v4/sports",
            params={"apiKey": ODDS_API_KEY},
            timeout=10,
        )
        remaining = r.headers.get("x-requests-remaining", "?")
        used = r.headers.get("x-requests-used", "?")
        if r.status_code == 200:
            return f"✅ Utilisées: {used} | Restantes: {remaining} (limite mensuelle)"
        elif r.status_code == 401:
            return "❌ 401 — Clé invalide"
        else:
            return f"❌ HTTP {r.status_code}"
    except Exception as e:
        return f"❌ Erreur: {e}"


print("=" * 50)
print("  QUOTAS API — Score Radar")
print("=" * 50)
print(f"\n1. API-Football (api-sports.io)")
print(f"   {check_api_football()}")
print(f"\n2. FootyStats (football-data-api.com)")
print(f"   {check_footystats()}")
print(f"\n3. The Odds API (the-odds-api.com)")
print(f"   {check_odds_api()}")
print()
