"""Score Radar — Dashboard Web."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

app = FastAPI(title="Score Radar Dashboard")
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

def _get_all_rows():
    from google_sheets import _get_sheet
    ws = _get_sheet()
    if not ws:
        return []
    return ws.get_all_values()[1:]

def _parse_rows(rows):
    parsed = []
    for row in rows:
        if len(row) < 10:
            continue
        result = row[9].strip() if len(row) > 9 else ""
        if not row[3].strip() or not row[0].strip():
            continue
        if not (result.startswith("Win") or result in ("Lose", "En cours")):
            continue
        try:
            conf = int(float(row[7].strip().replace("%", "") or "0"))
        except (ValueError, TypeError):
            conf = 0
        parsed.append({
            "date": row[0].strip(),
            "heure": row[1].strip(),
            "league": row[2].strip(),
            "teams": row[3].strip(),
            "score": row[4].strip(),
            "minute": row[5].strip(),
            "pick": row[6].strip(),
            "confidence": conf,
            "xg_debt": row[8].strip(),
            "result": "Win" if result.startswith("Win") else result,
            "team_pick": row[10].strip() if len(row) > 10 else "",
            "agg_pick": row[11].strip() if len(row) > 11 else "",
            "team_pick_result": row[12].strip() if len(row) > 12 else "",
            "agg_pick_result": row[13].strip() if len(row) > 13 else "",
        })
    # Déduplication : supprimer les lignes identiques (date+teams+pick+minute)
    seen = set()
    deduped = []
    for p in parsed:
        key = (p["date"], p["teams"], p["pick"], p["minute"])
        if key not in seen:
            seen.add(key)
            deduped.append(p)
    return deduped

@app.get("/api/stats")
async def api_stats():
    rows = _get_all_rows()
    picks = _parse_rows(rows)

    finished = [p for p in picks if p["result"].startswith("Win") or p["result"] == "Lose"]
    en_cours = [p for p in picks if p["result"] == "En cours"]
    wins = sum(1 for p in finished if p["result"].startswith("Win"))
    loses = sum(1 for p in finished if p["result"] == "Lose")
    total = wins + loses
    wr = round(wins / total * 100, 1) if total > 0 else 0

    # ROI simple (win = +1u, lose = -1u)
    roi = round((wins - loses) / total * 100, 1) if total > 0 else 0

    # Streak
    streak = 0
    streak_type = ""
    for p in reversed(finished):
        if not streak_type:
            streak_type = p["result"]
            streak = 1
        elif p["result"] == streak_type:
            streak += 1
        else:
            break

    # Par ligue
    by_league = defaultdict(lambda: {"wins": 0, "loses": 0, "picks": []})
    for p in finished:
        lg = p["league"] or "Autre"
        if p["result"].startswith("Win"):
            by_league[lg]["wins"] += 1
        else:
            by_league[lg]["loses"] += 1
        by_league[lg]["picks"].append({
            "date": p["date"],
            "teams": p["teams"],
            "score": p["score"],
            "minute": p["minute"],
            "pick": p["pick"],
            "confidence": p["confidence"],
            "result": p["result"],
        })

    leagues = []
    for lg, data in sorted(by_league.items(), key=lambda x: (x[1]["wins"] / (x[1]["wins"] + x[1]["loses"]) if (x[1]["wins"] + x[1]["loses"]) > 0 else 0), reverse=True):
        lt = data["wins"] + data["loses"]
        leagues.append({
            "name": lg,
            "wins": data["wins"],
            "loses": data["loses"],
            "total": lt,
            "wr": round(data["wins"] / lt * 100, 1) if lt > 0 else 0,
            "picks": list(reversed(data["picks"])),
        })

    # Winrate par jour (pour le graphique)
    by_date = defaultdict(lambda: {"wins": 0, "loses": 0})
    for p in finished:
        by_date[p["date"]]["wins" if p["result"].startswith("Win") else "loses"] += 1

    daily = []
    cumul_w, cumul_l = 0, 0
    for d in sorted(by_date.keys(), key=lambda x: datetime.strptime(x, "%d/%m/%Y") if "/" in x else datetime.min):
        cumul_w += by_date[d]["wins"]
        cumul_l += by_date[d]["loses"]
        ct = cumul_w + cumul_l
        daily.append({
            "date": d,
            "wins": by_date[d]["wins"],
            "loses": by_date[d]["loses"],
            "cumul_wr": round(cumul_w / ct * 100, 1) if ct > 0 else 0,
            "cumul_roi": round((cumul_w - cumul_l) / ct * 100, 1) if ct > 0 else 0,
        })

    # Derniers picks — groupés par match (teams + date)
    from collections import OrderedDict
    match_map = OrderedDict()
    for p in finished:
        key = (p["date"], p["teams"])
        if key not in match_map:
            match_map[key] = {
                "date": p["date"],
                "league": p["league"],
                "teams": p["teams"],
                "picks": [],
            }
        match_map[key]["picks"].append({
            "heure": p["heure"],
            "minute": p["minute"],
            "pick": p["pick"],
            "confidence": p["confidence"],
            "score": p["score"],
            "result": p["result"],
            "team_pick": p.get("team_pick", ""),
            "agg_pick": p.get("agg_pick", ""),
            "team_pick_result": p.get("team_pick_result", ""),
            "agg_pick_result": p.get("agg_pick_result", ""),
        })
    # Trier chaque match : picks par minute croissante
    for v in match_map.values():
        v["picks"].sort(key=lambda x: int(x["minute"].replace("'","").split("+")[0]) if x["minute"].replace("'","").split("+")[0].isdigit() else 0)
        # Score final = score du dernier pick
        v["score"] = v["picks"][-1]["score"] if v["picks"] else ""
        # Résumé : Xw Yl
        w = sum(1 for pk in v["picks"] if pk["result"] == "Win")
        l = sum(1 for pk in v["picks"] if pk["result"] == "Lose")
        v["summary"] = "%dW %dL" % (w, l)
        v["has_win"] = w > 0
        v["all_lose"] = l > 0 and w == 0
    last_picks = list(reversed(list(match_map.values())))

    return {
        "total_picks": total,
        "wins": wins,
        "loses": loses,
        "winrate": wr,
        "roi": roi,
        "streak": streak,
        "streak_type": streak_type,
        "en_cours_count": len(en_cours),
        "leagues": leagues,
        "daily": daily,
        "last_picks": last_picks,
    }

@app.get("/", response_class=HTMLResponse)
async def index():
    with open(os.path.join(os.path.dirname(__file__), "static", "index.html"), "r") as f:
        return f.read()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
