"""Twitter/X bot — daily recap, weekly thread, weekend teaser."""

import tweepy
import logging
import random
from datetime import datetime, timedelta
from collections import defaultdict
from config import (
    TWITTER_API_KEY as API_KEY,
    TWITTER_API_SECRET as API_SECRET,
    TWITTER_ACCESS_TOKEN as ACCESS_TOKEN,
    TWITTER_ACCESS_SECRET as ACCESS_SECRET,
)

logger = logging.getLogger(__name__)

POSITIVE_PHRASES = [
    "La regularite paie, encore une journee solide",
    "L'algorithme a bien travaille aujourd'hui",
    "Les stats ne mentent pas",
    "Journee propre, on continue",
    "Le modele confirme, la data a parle",
    "Encore un jour dans le vert",
    "Solide. Le process fonctionne",
    "La patience et la data, combo gagnant",
    "On ne change pas une methode qui marche",
    "Les chiffres parlent d'eux-memes",
    "Quand la data guide, les resultats suivent",
    "Bonne lecture des matchs aujourd'hui",
    "Signal detecte, signal valide",
    "Le radar etait bien calibre ce soir",
    "Journee verte, on enchaine",
]

NEGATIVE_PHRASES = [
    "Journee compliquee, ca fait partie du jeu",
    "Pas notre meilleur jour, mais le long terme est la",
    "Les Loses font partie du process. On revient demain",
    "Le football reste imprevisible, la methode reste fiable",
    "Rouge aujourd'hui, vert demain. C'est le jeu",
    "Meme les meilleurs algos ont des jours off",
    "On ne gagne pas tous les jours, mais on reste rentable",
    "Pas de panique, le modele est fait pour le long terme",
    "Journee rouge, mais la courbe reste ascendante",
    "Les stats etaient la, pas la reussite. Ca tourne",
    "La variance fait son travail. Nous aussi",
    "On absorbe et on avance",
    "Le modele reste solide malgre la journee",
    "Tous les tipsters ont des series, la difference c'est la methode",
    "Demain est un autre jour",
]

WEEKLY_POSITIVE = [
    "Semaine bouclée. Le radar reste affuté.",
    "Encore une semaine dans le vert. On continue.",
    "La data ne ment pas. Bilan positif.",
    "Process respecté, résultats au rendez-vous.",
    "Les chiffres parlent. On revient lundi.",
]

WEEKLY_NEGATIVE = [
    "Semaine mitigee, mais la courbe reste haussiere.",
    "Pas la meilleure semaine, le rebond arrive.",
    "On reste focus, la methode est rentable sur la duree.",
]

HASHTAGS = "#TeamParieur #ParisSportifs #PronoFoot #Betting #Football"

TWEET_LIMIT = 270  # marge de sécurité sous la limite X de 280

def _jlen(lines):
    """Longueur exacte du tweet si on joint les lignes par \\n."""
    return sum(len(l) for l in lines) + max(0, len(lines) - 1)

def _sanitize(tweets):
    """Filet de sécurité final : tronque tout tweet qui dépasse 280 chars."""
    out = []
    for t in tweets:
        if len(t) > 280:
            logger.warning("Tweet tronqué (%d→280) : %s…", len(t), t[:50])
            t = t[:279] + "…"
        out.append(t)
    return out


def get_twitter_client():
    """Cree un client Twitter API v2."""
    if not all([API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_SECRET]):
        raise ValueError("Credentials Twitter manquants dans .env (TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET)")
    return tweepy.Client(
        consumer_key=API_KEY,
        consumer_secret=API_SECRET,
        access_token=ACCESS_TOKEN,
        access_token_secret=ACCESS_SECRET,
        wait_on_rate_limit=True,
    )


def test_twitter_connection() -> str:
    """Teste la connexion Twitter. Retourne un message de statut."""
    try:
        client = get_twitter_client()
        me = client.get_me()
        if me and me.data:
            return f"OK — connecte en tant que @{me.data.username}"
        return "OK — connecte (pas de username retourne)"
    except ValueError as e:
        return f"ERREUR config: {e}"
    except tweepy.errors.Unauthorized as e:
        return f"ERREUR 401 — Credentials invalides ou revoquees: {e}"
    except tweepy.errors.Forbidden as e:
        return f"ERREUR 403 — Acces refuse (verifier les permissions de l'app sur developer.twitter.com): {e}"
    except Exception as e:
        return f"ERREUR: {type(e).__name__}: {e}"


def post_tweet(text, reply_to=None):
    """Poste un tweet. Retourne le tweet ID ou None."""
    try:
        if len(text) > 280:
            logger.warning("Tweet envoyé trop long (%d chars), tronqué à 280", len(text))
            text = text[:279] + "…"
        client = get_twitter_client()
        kwargs = {"text": text}
        if reply_to:
            kwargs["reply"] = {"in_reply_to_tweet_id": reply_to}
        response = client.create_tweet(**kwargs)
        tweet_id = response.data["id"]
        logger.info("Tweet poste (id=%s): %s", tweet_id, text[:60])
        return tweet_id
    except tweepy.errors.Unauthorized as e:
        logger.error("Tweet ERREUR 401 — credentials invalides ou revoquees: %s", e)
    except tweepy.errors.Forbidden as e:
        logger.error("Tweet ERREUR 403 — acces refuse (verifier permissions app Twitter): %s", e)
    except tweepy.errors.TooManyRequests as e:
        logger.error("Tweet ERREUR 429 — rate limit atteint: %s", e)
    except ValueError as e:
        logger.error("Tweet ERREUR config: %s", e)
    except Exception as e:
        logger.error("Tweet ERREUR inattendue (%s): %s", type(e).__name__, e)
    return None


def post_thread(tweets):
    """Poste un thread (liste de tweets). Retourne la liste des IDs."""
    ids = []
    prev_id = None
    for text in tweets:
        tweet_id = post_tweet(text, reply_to=prev_id)
        if tweet_id:
            ids.append(tweet_id)
            prev_id = tweet_id
        else:
            logger.error("Thread interrompu apres %d tweets", len(ids))
            break
    return ids


# --- Daily recap ---

def build_daily_recap(results):
    """Construit le recap quotidien. Retourne une LISTE de tweets (thread si > 280 chars)."""
    if not results:
        return None

    today = datetime.now().strftime("%d/%m")
    wins = sum(1 for r in results if r.get("result") == "Win")
    loses = sum(1 for r in results if r.get("result") == "Lose")
    total = wins + loses
    if total == 0:
        return None

    is_positive = wins >= loses
    wr = round(wins / total * 100) if total > 0 else 0
    phrase = random.choice(POSITIVE_PHRASES if is_positive else NEGATIVE_PHRASES)

    by_league = defaultdict(list)
    for r in results:
        by_league[r.get("league", "Autre")].append(r)

    top5 = sorted(
        [r for r in results if r.get("result") == "Win"],
        key=lambda x: int(str(x.get("confidence", "0")).replace("%", "") or "0"),
        reverse=True,
    )[:5]

    def _match_line(r):
        icon = "✅" if r.get("result") == "Win" else "❌"
        score = str(r.get("home_goals", "?")) + "-" + str(r.get("away_goals", "?"))
        return icon + " " + r.get("home", "?") + " " + score + " " + r.get("away", "?") + " — " + r.get("pick", "?")

    # Try single tweet
    joiner = chr(10)
    simple = ["⚡ Score Radar " + today, ""]
    for r in results:
        simple.append(_match_line(r))
    simple += ["", "Bilan : " + str(wins) + "W/" + str(loses) + "L (" + str(wr) + "%)", phrase, "", HASHTAGS]
    single_text = joiner.join(simple)

    if len(single_text) <= 280:
        return [single_text]

    # Thread mode
    tweets = []

    # Tweet 1: Header + TOP N (dynamique pour rester sous 280 chars)
    footer_t1 = ["", "Bilan : " + str(wins) + "W/" + str(loses) + "L (" + str(wr) + "%)", "", "↓ Detail par ligue"]
    selected_top = []
    for r in top5:
        score = str(r.get("home_goals", "?")) + "-" + str(r.get("away_goals", "?"))
        line = "✅ " + r.get("home", "?") + " " + score + " " + r.get("away", "?") + " — " + r.get("pick", "?")
        candidate = ["⚡ Score Radar " + today, "", "⭐ TOP " + str(len(selected_top) + 1)] + selected_top + [line] + footer_t1
        if len(joiner.join(candidate)) <= 278:
            selected_top.append(line)
        else:
            break
    t1 = ["⚡ Score Radar " + today, ""]
    if selected_top:
        t1.append("⭐ TOP " + str(len(selected_top)))
        t1.extend(selected_top)
    t1.extend(footer_t1)
    tweets.append(joiner.join(t1))

    # Tweets par ligue — on accumule ligne par ligne sans jamais dépasser TWEET_LIMIT
    sorted_leagues = sorted(by_league.items(), key=lambda x: len(x[1]), reverse=True)
    cur = []

    def flush_cur():
        if cur:
            tweets.append(joiner.join(cur))
        cur.clear()

    def add_line(line):
        """Ajoute une ligne au buffer, flush d'abord si ça dépasserait TWEET_LIMIT."""
        if _jlen(cur + [line]) > TWEET_LIMIT and cur:
            flush_cur()
        cur.append(line)

    for league, lr in sorted_leagues:
        lw = sum(1 for r in lr if r.get("result") == "Win")
        ll = sum(1 for r in lr if r.get("result") == "Lose")
        add_line("🏆 " + league)
        for r in lr:
            add_line(_match_line(r))
        add_line(str(lw) + "W/" + str(ll) + "L")
        add_line("")
    flush_cur()

    # Dernier tweet: bilan
    final = ["📊 " + str(total) + " picks | " + str(wins) + "W " + str(loses) + "L | " + str(wr) + "% WR",
             "", phrase, "", HASHTAGS]
    tweets.append(joiner.join(final))
    return _sanitize(tweets)

def build_weekend_teaser(match_count):
    """Construit le tweet teaser du week-end."""
    templates = [
        str(match_count) + " matchs sous surveillance aujourd'hui\n\nResultats ce soir\n\n" + HASHTAGS,
        "Le radar est branche\n\n" + str(match_count) + " matchs analyses en temps reel\n\nRecap ce soir 23h\n\n" + HASHTAGS,
        str(match_count) + " matchs dans le viseur\n\nL'algorithme tourne, les alertes arrivent\n\nBilan ce soir\n\n" + HASHTAGS,
    ]
    return random.choice(templates)


# --- Weekly thread ---


def build_weekly_thread(results):
    """Construit un thread de recap hebdomadaire.

    Tweet 1: TOP PICKS de la semaine (format explicite, limite 280 chars)
    Tweet 2+: Resultats par ligue
    Dernier tweet: Bilan global + phrase + hashtags
    """
    if not results:
        return []

    wins = [r for r in results if r.get("result") == "Win"]
    loses = [r for r in results if r.get("result") == "Lose"]
    total_w = len(wins)
    total_l = len(loses)
    total = total_w + total_l
    if total == 0:
        return []

    wr = round(total_w / total * 100)
    is_positive = total_w >= total_l

    tweets = []

    # --- Tweet 1: TOP PICKS (dynamique selon limite 280 chars) ---
    top_candidates = sorted(wins, key=lambda x: x.get("confidence", 0), reverse=True)[:5]

    header = "\U0001f4ca RECAP SEMAINE | Score Radar"
    title = "\u2b50 TOP PICKS"
    footer = "Bilan : " + str(total_w) + "W/" + str(total_l) + "L (" + str(wr) + "% WR)" + chr(10) + "#TeamParieur #ParisSportifs" + chr(10) + "\u2193 Detail par ligue ci-dessous"
    LIMIT = 278

    pick_lines = []
    for i, r in enumerate(top_candidates, 1):
        score_at = str(r.get("home_goals", "?")) + "-" + str(r.get("away_goals", "?"))
        minute = r.get("minute", "")
        pick = r.get("pick", "?")
        result_icon = "\u2705" if r.get("result") == "Win" else "\u274c"
        home = r.get("home", "?")
        away = r.get("away", "?")
        minute_part = " \u23f1" + minute + "'" if minute else ""
        line = str(i) + ". " + home + " " + score_at + " " + away + minute_part + " \u2192 " + pick + " " + result_icon
        pick_lines.append(line)

    # Ajouter des picks jusqu'a la limite de 280 chars
    selected = []
    for line in pick_lines:
        candidate = "\n".join([header, "", title, ""] + selected + [line, "", footer])
        if len(candidate) <= LIMIT:
            selected.append(line)
        else:
            break

    if not selected and pick_lines:
        selected = [pick_lines[0]]  # Au moins 1 pick

    t1_content = "\n".join([header, "", title, ""] + selected + ["", footer])
    tweets.append(t1_content)

    # --- Tweets 2+: par ligue (decoupage ligne par ligne, jamais > TWEET_LIMIT) ---
    by_league = defaultdict(list)
    for r in results:
        league = r.get("league", "Autre")
        by_league[league].append(r)

    sorted_leagues = sorted(by_league.items(), key=lambda x: len(x[1]), reverse=True)

    current_lines = []

    def flush():
        if current_lines:
            tweets.append(chr(10).join(current_lines))
            current_lines.clear()

    def try_add(line):
        """Ajoute une ligne, flush d'abord si ça dépasserait TWEET_LIMIT."""
        if _jlen(current_lines + [line]) > TWEET_LIMIT and current_lines:
            flush()
        current_lines.append(line)

    for league, league_results in sorted_leagues:
        league_w = sum(1 for r in league_results if r.get("result") == "Win")
        league_l = sum(1 for r in league_results if r.get("result") == "Lose")

        match_lines = []
        for r in league_results:
            icon = "✅" if r.get("result") == "Win" else "❌"
            score = str(r.get("home_goals", "?")) + "-" + str(r.get("away_goals", "?"))
            ml = icon + " " + r.get("home", "?") + " " + score + " " + r.get("away", "?") + " — " + r.get("pick", "?")
            match_lines.append(ml)
        summary = str(league_w) + "W/" + str(league_l) + "L"

        block_lines = ["🏆 " + league] + match_lines + [summary, ""]
        # Si le bloc entier tient avec le buffer courant, on l'ajoute d'un coup
        if _jlen(current_lines + block_lines) <= TWEET_LIMIT:
            current_lines.extend(block_lines)
        elif _jlen(block_lines) <= TWEET_LIMIT:
            # Le bloc tient seul : flush puis ajouter
            flush()
            current_lines.extend(block_lines)
        else:
            # Trop grand : ligne par ligne
            for line in block_lines:
                try_add(line)

    flush()

    # --- Dernier tweet: bilan + phrase + hashtags ---
    phrase = random.choice(WEEKLY_POSITIVE if is_positive else WEEKLY_NEGATIVE)
    final_lines = []
    final_lines.append("\U0001f4c8 BILAN SEMAINE")
    final_lines.append("")
    final_lines.append(str(total) + " picks | " + str(total_w) + "W " + str(total_l) + "L | " + str(wr) + "% WR")
    final_lines.append("")
    final_lines.append(phrase)
    final_lines.append("")
    final_lines.append("On revient lundi \U0001f680")
    final_lines.append("")
    final_lines.append(HASHTAGS)

    tweets.append("\n".join(final_lines))

    return _sanitize(tweets)
