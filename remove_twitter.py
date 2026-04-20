"""
Supprime toute la fonctionnalité Twitter/tweet du bot.
"""

BOT_PATH = "/root/telegram-goal-bot/bot.py"

with open(BOT_PATH, "r", encoding="utf-8") as f:
    content = f.read()

# ── 1. Supprimer l'import Twitter ─────────────────────────────────────────────

OLD_IMPORT = """from twitter import (
    build_daily_recap, build_weekend_teaser, build_weekly_thread,
    post_tweet, post_thread,
)"""

assert OLD_IMPORT in content, "Import twitter non trouvé"
content = content.replace(OLD_IMPORT, "", 1)

# ── 2. Supprimer les 3 fonctions Twitter + le bloc commentaire ─────────────────

OLD_TWITTER_FUNCS = """\


# --- Twitter scheduled jobs ---

async def send_daily_tweet(context: ContextTypes.DEFAULT_TYPE) -> None:
    \"\"\"Poste le recap quotidien sur Twitter (22h UTC = 23h Paris).\"\"\"
    try:
        rows = get_all_rows()
    except Exception as e:
        logger.error("Tweet recap: erreur sheet: %s", e)
        return

    today_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    today_results = []
    for row in rows:
        if len(row) < 10:
            continue
        if row[0].strip() != today_str:
            continue
        result_val = row[10].strip() if len(row) > 10 else ""
        if not (result_val.startswith("Win") or result_val == "Lose"):
            continue
        teams = row[3].strip()
        parts = teams.split(" - ") if " - " in teams else [teams, ""]
        score = row[4].strip()
        sp = score.split(" - ") if " - " in score else ["0", "0"]
        today_results.append({
            "home": parts[0].strip(),
            "away": parts[1].strip() if len(parts) > 1 else "",
            "home_goals": sp[0].strip(),
            "away_goals": sp[1].strip() if len(sp) > 1 else "0",
            "pick": row[6].strip(),
            "confidence": row[7].strip(),
            "result": "Win" if result_val.startswith("Win") else result_val,
            "league": row[2].strip() if len(row) > 2 else "Autre",
        })

    if not today_results:
        logger.info("Tweet recap: aucun resultat aujourd'hui, skip")
        return

    tweets = build_daily_recap(today_results)
    if tweets:
        if len(tweets) == 1:
            post_tweet(tweets[0])
            logger.info("Tweet recap quotidien poste (1 tweet)")
        else:
            ids = post_thread(tweets)
            logger.info("Thread recap quotidien poste: %d tweets", len(ids))


async def send_weekend_teaser(context: ContextTypes.DEFAULT_TYPE) -> None:
    \"\"\"Poste le teaser du week-end sur Twitter (11h UTC = 12h Paris).\"\"\"
    try:
        from footystats import get_todays_matches as _gtm
        matches = await _gtm()
        count = len(matches)
    except Exception:
        count = 0

    if count > 0:
        tweet_text = build_weekend_teaser(count)
        post_tweet(tweet_text)


async def send_weekly_tweet(context: ContextTypes.DEFAULT_TYPE) -> None:
    \"\"\"Poste le thread recap hebdomadaire sur Twitter (dimanche 22h30 UTC).\"\"\"
    try:
        from google_sheets import get_week_results
        results = get_week_results()
    except Exception as e:
        logger.error("Tweet weekly: erreur sheet: %s", e)
        return

    if not results:
        logger.info("Tweet weekly: aucun resultat cette semaine, skip")
        return

    # Enrichir avec la ligue si disponible
    for r in results:
        if "league" not in r or not r["league"]:
            r["league"] = "Autre"

    tweets = build_weekly_thread(results)
    if tweets:
        ids = post_thread(tweets)
        logger.info("Thread weekly poste: %d tweets", len(ids))


# --- Main ---"""

NEW_TWITTER_FUNCS = """\


# --- Main ---"""

assert OLD_TWITTER_FUNCS in content, "Bloc fonctions Twitter non trouvé"
content = content.replace(OLD_TWITTER_FUNCS, NEW_TWITTER_FUNCS, 1)

# ── 3. Supprimer les schedulers Twitter dans main() ────────────────────────────

OLD_SCHEDULERS = """\

    # Twitter schedulers
    from datetime import time as dt_time
    # Daily recap: 22h UTC (23h Paris) tous les jours
    job_queue.run_daily(send_daily_tweet, time=dt_time(hour=22, minute=0))
    # Weekend teaser: 11h UTC (12h Paris) samedi + dimanche
    job_queue.run_daily(send_weekend_teaser, time=dt_time(hour=11, minute=0), days=(5, 6))
    # Weekly thread: dimanche 23h00 UTC (minuit Paris heure d'hiver)
    job_queue.run_daily(send_weekly_tweet, time=dt_time(hour=23, minute=0), days=(6,))

    print("[OK] Goal Signal Bot demarre !")"""

NEW_SCHEDULERS = """\

    print("[OK] Goal Signal Bot demarre !")"""

assert OLD_SCHEDULERS in content, "Bloc schedulers Twitter non trouvé"
content = content.replace(OLD_SCHEDULERS, NEW_SCHEDULERS, 1)

with open(BOT_PATH, "w", encoding="utf-8") as f:
    f.write(content)

print("bot.py OK — Twitter supprimé")
