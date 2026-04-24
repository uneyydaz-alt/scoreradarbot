import os
from dotenv import load_dotenv

load_dotenv()

VALUE_BOT_TOKEN  = os.getenv("VALUE_BOT_TOKEN", "")
ODDS_API_KEY     = os.getenv("ODDS_API_KEY", "")
ADMIN_CHAT_ID    = int(os.getenv("VALUE_BOT_ADMIN_ID", "0"))

MIN_EDGE         = float(os.getenv("VALUE_BOT_MIN_EDGE", "0.04"))   # 4% par défaut
CHECK_INTERVAL   = int(os.getenv("VALUE_BOT_CHECK_INTERVAL", "3600"))  # 1h par défaut

# Ligues pour le monitoring live (budget limité — free tier 500 req/mois)
LIVE_SPORTS = [
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_france_ligue_one",
    "soccer_italy_serie_a",
    "soccer_uefa_champs_league",
]

# Ligues pour le digest matin (check unique, plus large)
DIGEST_SPORTS = LIVE_SPORTS + [
    "soccer_germany_bundesliga",
    "soccer_portugal_primeira_liga",
    "soccer_netherlands_eredivisie",
    "soccer_uefa_europa_league",
    "soccer_belgium_first_div",
]

# Bookmakers à comparer (Pinnacle = référence, les autres = soft books)
# Winamax / Betclic ajoutés si disponibles dans The Odds API (à vérifier)
SOFT_BOOKS = [
    "winamax_fr",
    "betclic",
    "bet365",
    "unibet",
    "bwin",
    "betway",
    "williamhill",
]
