import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")
API_FOOTBALL_BASE_URL = "https://v3.football.api-sports.io"

FOOTYSTATS_API_KEY = os.getenv("FOOTYSTATS_API_KEY", "")
FOOTYSTATS_BASE_URL = "https://api.football-data-api.com"

# Google Sheets
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "")

# Seuil de confiance par défaut (0-100)
DEFAULT_CONFIDENCE_THRESHOLD = int(os.getenv("DEFAULT_CONFIDENCE_THRESHOLD", "65"))

# Canal Telegram où envoyer les alertes (en plus des DM)
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@scoreradarbot")

# Stripe
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")

# Admin Telegram ID (pour /activate manuel)
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Canal privé premium (ID numérique, ex: -1001234567890)
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

# Fichier des membres grandfathered (ne jamais kick)
GRANDFATHERED_FILE = "grandfathered.json"

# Paliers parrainage (nombre de filleuls payants -> récompense)
REFERRAL_TIERS = {
    3: {"reward": "monthly", "label": "1 mois gratuit"},
    5: {"reward": "semestrial_3m", "label": "3 mois gratuits"},
    10: {"reward": "semestrial", "label": "6 mois gratuits"},
    20: {"reward": "lifetime", "label": "Acces a vie"},
}

# Plans d'abonnement
PLANS = {
    "trial": {"name": "Essai Gratuit", "duration_days": 3, "price": 0, "stars": 0},
    "monthly": {"name": "Mensuel", "duration_days": 30, "price": 999, "stars": 750},         # ~14.6€ (couvre 30% commission)
    "semestrial": {"name": "6 Mois", "duration_days": 180, "price": 4499, "stars": 3300},    # 3300×0.0195×0.7 = ~45.0€ (≥44.99€ ✅)
    "lifetime": {"name": "Lifetime", "duration_days": None, "price": 7999, "stars": 5900},    # 5900×0.0195×0.7 = ~80.5€ (≥79.99€ ✅)
}

# Intervalle de vérification des matchs (en secondes)
CHECK_INTERVAL_SECONDS = 120

# Fichier de stockage des utilisateurs
USERS_FILE = "users.json"

# Ligues populaires (ID API-Football)
POPULAR_LEAGUES = {
    # --- Division 1 ---
    39: "Premier League",
    140: "La Liga",
    135: "Serie A",
    78: "Bundesliga",
    61: "Ligue 1",
    94: "Liga Portugal",
    88: "Eredivisie",
    144: "Jupiler Pro League",
    203: "Super Lig",
    235: "Russian Premier League",
    128: "Liga Argentina",
    71: "Brasileirao",
    253: "MLS",
    307: "Saudi Pro League",
    186: "Ligue 1 Algerie",
    188: "A-League",
    218: "Austria Bundesliga",
    265: "Primera Division Chile",
    169: "Chinese Super League",
    239: "Primera A Colombia",
    210: "HNL Croatie",
    119: "Superliga Danemark",
    242: "Liga Pro Equateur",
    383: "Ligat Ha'al Israel",
    98: "J1 League",
    262: "Liga MX",
    103: "Eliteserien",
    179: "Premiership Ecosse",
    207: "Super League Suisse",
    110: "Welsh Premier League",
    # --- Division 2 ---
    40: "Championship",
    141: "La Liga 2",
    136: "Serie B",
    79: "Bundesliga 2",
    62: "Ligue 2",
    95: "Liga Portugal 2",
    89: "Eerste Divisie",
    145: "Jupiler Pro League 2",
    204: "Super Lig 2",
    # --- Autres divisions ---
    875: "Segunda Division RFEF G1",
    876: "Segunda Division RFEF G2",
    877: "Segunda Division RFEF G3",
    878: "Segunda Division RFEF G4",
    879: "Segunda Division RFEF G5",
    80: "3. Liga Allemagne",
    # --- Coupes nationales ---
    45: "FA Cup",
    81: "DFB Pokal",
    137: "Coppa Italia",
    143: "Copa del Rey",
    96: "Taca de Portugal",
    556: "Supercopa de Espana",
    # --- Coupes internationales ---
    2: "Champions League",
    3: "Europa League",
    848: "Conference League",
    1: "World Cup",
    4: "Euro",
    15: "FIFA Club World Cup",
    13: "Copa Libertadores",
    9: "Copa America",
    11: "Copa Sudamericana",
    17: "AFC Champions League",
    5: "Nations League",
    32: "WC Qualif. Europe",
    960: "Euro Qualifications",
    10: "International Friendlies",
    525: "UEFA Champions League Women",
}
