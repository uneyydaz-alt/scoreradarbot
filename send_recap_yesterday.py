import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timezone, timedelta
from google_sheets import get_all_rows
from twitter_bot import build_daily_recap, post_tweet, post_thread

yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%d/%m/%Y")
print("Recap pour le", yesterday)

rows = get_all_rows()
results = []
for row in rows:
    if len(row) < 10:
        continue
    if row[0].strip() != yesterday:
        continue
    result_val = row[9].strip()
    if not (result_val.startswith("Win") or result_val == "Lose"):
        continue
    teams = row[3].strip()
    parts = teams.split(" - ") if " - " in teams else [teams, ""]
    score = row[4].strip()
    sp = score.split(" - ") if " - " in score else ["0", "0"]
    results.append({
        "home": parts[0].strip(),
        "away": parts[1].strip() if len(parts) > 1 else "",
        "home_goals": sp[0].strip(),
        "away_goals": sp[1].strip() if len(sp) > 1 else "0",
        "pick": row[6].strip(),
        "confidence": row[7].strip(),
        "result": "Win" if result_val.startswith("Win") else result_val,
        "league": row[2].strip() if len(row) > 2 else "Autre",
    })

if not results:
    print("Aucun resultat trouve pour hier.")
    sys.exit(0)

print(len(results), "resultat(s) trouve(s)")
tweets = build_daily_recap(results)
if not tweets:
    print("build_daily_recap a retourne rien.")
    sys.exit(0)

for i, tw in enumerate(tweets):
    print("--- Tweet", i+1, "---")
    print(tw)
    print()

if len(tweets) == 1:
    post_tweet(tweets[0])
    print("Tweet envoye.")
else:
    ids = post_thread(tweets)
    print("Thread envoye:", len(ids), "tweets.")
