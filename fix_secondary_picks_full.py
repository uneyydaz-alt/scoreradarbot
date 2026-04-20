"""
Fix complet : résultats exacts pour team_pick et agg_pick.

Problème : team_pick est en col K, update_result écrase col K avec Win/Lose.
Solution :
  - log_alert : "" en col K (réservé au résultat), team_pick en col L, agg_pick en col M
  - bot.py    : stocke dominant_side + dom_goals_at_alert dans _pending_results
  - update_result : calcule team_pick_win, écrit en col N et O
  - server.py : lit team_pick/agg_pick depuis cols L/M, résultats depuis cols N/O
  - index.html : affiche ✅/❌ pour les picks secondaires
"""

import re

# ─────────────────────────────────────────────────────────────────────────────
# 1. google_sheets.py
# ─────────────────────────────────────────────────────────────────────────────

GS_PATH = "/root/telegram-goal-bot/google_sheets.py"

with open(GS_PATH, "r", encoding="utf-8") as f:
    gs = f.read()

# 1a. log_alert : déplacer team_pick/agg_pick de col K/L vers L/M
#     (laisser col K vide pour update_result)

OLD_LOG_ALERT_ROW = '''\
        # Picks secondaires (equipe + agressif)
        dominant_team = signal.get("dominant_team", "")
        dominant_side = signal.get("dominant_side", "home")
        dom_goals = home_goals if dominant_side == "home" else away_goals
        team_pick = "Over %.1f %s" % (dom_goals + 0.5, dominant_team) if dominant_team else ""
        agg_pick = ("Prochain but \u2014 %s" % dominant_team) if dominant_team else ""

        row = [
            now.strftime("%d/%m/%Y"),
            now.strftime("%H:%M"),
            league,
            team_str,
            "%d - %d" % (home_goals, away_goals),
            "%d\'" % elapsed,
            pick,
            "%d%%" % confidence,
            "%.2f" % xg_debt,
            "En cours",
            team_pick,
            agg_pick,
        ]'''

NEW_LOG_ALERT_ROW = '''\
        # Picks secondaires (equipe + agressif)
        dominant_team = signal.get("dominant_team", "")
        dominant_side = signal.get("dominant_side", "home")
        dom_goals = home_goals if dominant_side == "home" else away_goals
        team_pick = "Over %.1f %s" % (dom_goals + 0.5, dominant_team) if dominant_team else ""
        agg_pick = ("Prochain but \u2014 %s" % dominant_team) if dominant_team else ""

        row = [
            now.strftime("%d/%m/%Y"),
            now.strftime("%H:%M"),
            league,
            team_str,
            "%d - %d" % (home_goals, away_goals),
            "%d\'" % elapsed,
            pick,
            "%d%%" % confidence,
            "%.2f" % xg_debt,
            "En cours",
            "",         # col K : réservé au résultat principal (update_result)
            team_pick,  # col L
            agg_pick,   # col M
        ]'''

assert OLD_LOG_ALERT_ROW in gs, "Pattern log_alert row non trouvé dans google_sheets.py"
gs = gs.replace(OLD_LOG_ALERT_ROW, NEW_LOG_ALERT_ROW, 1)

# 1b. log_alert : étendre le formatage jaune de K à M
OLD_FORMAT_YELLOW = '        sheet.format("A%d:K%d" % (row_num, row_num), {\n            "backgroundColor": COLOR_YELLOW,\n        })\n\n        return row_num'
NEW_FORMAT_YELLOW = '        sheet.format("A%d:M%d" % (row_num, row_num), {\n            "backgroundColor": COLOR_YELLOW,\n        })\n\n        return row_num'

assert OLD_FORMAT_YELLOW in gs, "Pattern format jaune non trouvé"
gs = gs.replace(OLD_FORMAT_YELLOW, NEW_FORMAT_YELLOW, 1)

# 1c. update_result : accepter team_pick_win, écrire en col N+O, étendre format
OLD_UPDATE_RESULT = '''\
def update_result(row_nums, final_score_str, final_goals, fixture_id=None):
    """Met à jour le résultat final de toutes les alertes d\'un match."""
    sheet = _get_sheet()
    if sheet is None:
        return

    if isinstance(row_nums, int):
        row_nums = [row_nums]

    try:
        for row_num in row_nums:
            try:
                score_cell = sheet.cell(row_num, 5).value  # Colonne E = SCORE (alerte)
                if score_cell and " - " in score_cell:
                    parts = score_cell.split(" - ")
                    goals_at_alert = int(parts[0].strip()) + int(parts[1].strip())
                else:
                    goals_at_alert = 0

                goal_after = final_goals > goals_at_alert
                result = "Win" if goal_after else "Lose"
                color = COLOR_GREEN if goal_after else COLOR_RED

                sheet.update("K%d" % row_num, [[result]])
                sheet.format("A%d:K%d" % (row_num, row_num), {
                    "backgroundColor": color,
                })

                logger.info("Google Sheets: ligne %d -> %s (score: %s)", row_num, result, final_score_str)

            except Exception as e:
                logger.error("Erreur update ligne %d: %s", row_num, e)

    except Exception as e:
        logger.error("Erreur mise a jour Google Sheets: %s", e)
        global _sheet
        _sheet = None'''

NEW_UPDATE_RESULT = '''\
def update_result(row_nums, final_score_str, final_goals, fixture_id=None, team_pick_win=None):
    """Met à jour le résultat final de toutes les alertes d\'un match."""
    sheet = _get_sheet()
    if sheet is None:
        return

    if isinstance(row_nums, int):
        row_nums = [row_nums]

    try:
        for row_num in row_nums:
            try:
                score_cell = sheet.cell(row_num, 5).value  # Colonne E = SCORE (alerte)
                if score_cell and " - " in score_cell:
                    parts = score_cell.split(" - ")
                    goals_at_alert = int(parts[0].strip()) + int(parts[1].strip())
                else:
                    goals_at_alert = 0

                goal_after = final_goals > goals_at_alert
                result = "Win" if goal_after else "Lose"
                color = COLOR_GREEN if goal_after else COLOR_RED

                sheet.update("K%d" % row_num, [[result]])

                # Résultat des picks secondaires (team_pick + agg_pick)
                if team_pick_win is not None:
                    tp_result = "Win" if team_pick_win else "Lose"
                    sheet.update("N%d" % row_num, [[tp_result, tp_result]])  # N=team_pick, O=agg_pick

                sheet.format("A%d:O%d" % (row_num, row_num), {
                    "backgroundColor": color,
                })

                logger.info("Google Sheets: ligne %d -> %s (score: %s)", row_num, result, final_score_str)

            except Exception as e:
                logger.error("Erreur update ligne %d: %s", row_num, e)

    except Exception as e:
        logger.error("Erreur mise a jour Google Sheets: %s", e)
        global _sheet
        _sheet = None'''

assert OLD_UPDATE_RESULT in gs, "Pattern update_result non trouvé"
gs = gs.replace(OLD_UPDATE_RESULT, NEW_UPDATE_RESULT, 1)

# 1d. finalize_row : étendre le format à col O
OLD_FINALIZE_FORMAT = '        sheet.format("A%d:K%d" % (row_num, row_num), {\n            "backgroundColor": color,\n        })\n        logger.info("Google Sheets: ligne %d -> %s (buts: %d vs %d à l\'alerte)",'
NEW_FINALIZE_FORMAT = '        sheet.format("A%d:O%d" % (row_num, row_num), {\n            "backgroundColor": color,\n        })\n        logger.info("Google Sheets: ligne %d -> %s (buts: %d vs %d à l\'alerte)",'

assert OLD_FINALIZE_FORMAT in gs, "Pattern finalize_row format non trouvé"
gs = gs.replace(OLD_FINALIZE_FORMAT, NEW_FINALIZE_FORMAT, 1)

with open(GS_PATH, "w", encoding="utf-8") as f:
    f.write(gs)

print("google_sheets.py OK")

# ─────────────────────────────────────────────────────────────────────────────
# 2. bot.py : stocker dominant_side + dom_goals_at_alert, passer team_pick_win
# ─────────────────────────────────────────────────────────────────────────────

BOT_PATH = "/root/telegram-goal-bot/bot.py"

with open(BOT_PATH, "r", encoding="utf-8") as f:
    bot = f.read()

# 2a. Stocker dominant_side et dom_goals_at_alert dans _pending_results
OLD_PENDING_ENTRY = '''\
                        if pick_key not in check_matches._pending_results:
                            check_matches._pending_results[pick_key] = {
                                "fixture_id": str(fixture_id),
                                "row_nums": [],
                                "home": info["home_team"],
                                "away": info["away_team"],
                                "goals_at_alert": total_goals,
                                "pick": "Over %.1f FT" % (total_goals + 0.5),
                                "notified_win": False,
                                "channel_message_id": sent_alert.message_id if sent_alert else None,
                            }'''

NEW_PENDING_ENTRY = '''\
                        if pick_key not in check_matches._pending_results:
                            _dom_side = signal.get("dominant_side", "")
                            _dom_goals_at_alert = info["home_goals"] if _dom_side == "home" else info["away_goals"]
                            check_matches._pending_results[pick_key] = {
                                "fixture_id": str(fixture_id),
                                "row_nums": [],
                                "home": info["home_team"],
                                "away": info["away_team"],
                                "goals_at_alert": total_goals,
                                "pick": "Over %.1f FT" % (total_goals + 0.5),
                                "notified_win": False,
                                "channel_message_id": sent_alert.message_id if sent_alert else None,
                                "dominant_side": _dom_side,
                                "dom_goals_at_alert": _dom_goals_at_alert,
                            }'''

assert OLD_PENDING_ENTRY in bot, "Pattern pending entry non trouvé dans bot.py"
bot = bot.replace(OLD_PENDING_ENTRY, NEW_PENDING_ENTRY, 1)

# 2b. Passer team_pick_win à update_result quand le match se termine
OLD_UPDATE_RESULT_CALL = '''\
                try:
                    update_result(pending["row_nums"], final_score, final_goals, fixture_id=fid)
                    logger.info("Resultat: %s vs %s -> score final: %s (%d lignes)",'''

NEW_UPDATE_RESULT_CALL = '''\
                try:
                    _dom_side_r = pending.get("dominant_side", "")
                    _dom_goals_at = pending.get("dom_goals_at_alert", 0)
                    if _dom_side_r:
                        _dom_final = fi["home_goals"] if _dom_side_r == "home" else fi["away_goals"]
                        _team_pick_win = _dom_final > _dom_goals_at
                    else:
                        _team_pick_win = None
                    update_result(pending["row_nums"], final_score, final_goals, fixture_id=fid, team_pick_win=_team_pick_win)
                    logger.info("Resultat: %s vs %s -> score final: %s (%d lignes)",'''

assert OLD_UPDATE_RESULT_CALL in bot, "Pattern update_result call non trouvé dans bot.py"
bot = bot.replace(OLD_UPDATE_RESULT_CALL, NEW_UPDATE_RESULT_CALL, 1)

with open(BOT_PATH, "w", encoding="utf-8") as f:
    f.write(bot)

print("bot.py OK")

# ─────────────────────────────────────────────────────────────────────────────
# 3. server.py : lire team_pick/agg_pick depuis cols L/M, résultats N/O
# ─────────────────────────────────────────────────────────────────────────────

SRV_PATH = "/root/telegram-goal-bot/web/server.py"

with open(SRV_PATH, "r", encoding="utf-8") as f:
    srv = f.read()

# 3a. _parse_rows : lire depuis les bonnes colonnes
OLD_PARSE_PICKS = '''\
            "team_pick": row[10].strip() if len(row) > 10 else "",
            "agg_pick": row[11].strip() if len(row) > 11 else "",'''

NEW_PARSE_PICKS = '''\
            "team_pick": row[11].strip() if len(row) > 11 else "",
            "agg_pick": row[12].strip() if len(row) > 12 else "",
            "team_pick_result": row[13].strip() if len(row) > 13 else "",
            "agg_pick_result": row[14].strip() if len(row) > 14 else "",'''

assert OLD_PARSE_PICKS in srv, "Pattern parse picks non trouvé dans server.py"
srv = srv.replace(OLD_PARSE_PICKS, NEW_PARSE_PICKS, 1)

# 3b. picks_append : transmettre team_pick_result et agg_pick_result
OLD_PICKS_APPEND = '''\
        match_map[key]["picks"].append({
            "heure": p["heure"],
            "minute": p["minute"],
            "pick": p["pick"],
            "confidence": p["confidence"],
            "score": p["score"],
            "result": p["result"],
            "team_pick": p.get("team_pick", ""),
            "agg_pick": p.get("agg_pick", ""),
        })'''

NEW_PICKS_APPEND = '''\
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
        })'''

assert OLD_PICKS_APPEND in srv, "Pattern picks_append non trouvé dans server.py"
srv = srv.replace(OLD_PICKS_APPEND, NEW_PICKS_APPEND, 1)

with open(SRV_PATH, "w", encoding="utf-8") as f:
    f.write(srv)

print("server.py OK")

# ─────────────────────────────────────────────────────────────────────────────
# 4. index.html : afficher ✅/❌ selon team_pick_result / agg_pick_result
# ─────────────────────────────────────────────────────────────────────────────

HTML_PATH = "/root/telegram-goal-bot/web/static/index.html"

with open(HTML_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# Trouver et remplacer le bloc des picks secondaires dans la modale
# Le pattern peut varier selon l'état actuel du fichier (avec ou sans badge ?)
# On cherche le bloc if(pk.team_pick) dans openModal

OLD_SECONDARY_BLOCK = '''\
if(pk.team_pick){
html+="<div class=\'pick-row\' style=\'opacity:.75;margin-left:16px\'>";
html+="<div><div class=\'pick-info\' style=\'font-size:.9rem\'>\u26bd "+pk.team_pick+"</div>";
html+="<div class=\'pick-meta\'>Pick \u00e9quipe</div></div>";
html+="<span class=\'result-badge "+cls+"\'>"+(pk.result==="Win"?"\u2753":"\u274c")+"</span>";
html+="</div>";
}
if(pk.agg_pick){
html+="<div class=\'pick-row\' style=\'opacity:.75;margin-left:16px\'>";
html+="<div><div class=\'pick-info\' style=\'font-size:.9rem\'>\u26a1 "+pk.agg_pick+"</div>";
html+="<div class=\'pick-meta\'>Pick agressif</div></div>";
html+="<span class=\'result-badge "+cls+"\'>"+(pk.result==="Win"?"\u2753":"\u274c")+"</span>";
html+="</div>";
}'''

NEW_SECONDARY_BLOCK = '''\
if(pk.team_pick){
html+="<div class=\'pick-row\' style=\'opacity:.75;margin-left:16px\'>";
html+="<div><div class=\'pick-info\' style=\'font-size:.9rem\'>\u26bd "+pk.team_pick+"</div>";
html+="<div class=\'pick-meta\'>Pick \u00e9quipe</div></div>";
if(pk.team_pick_result){var tcls=pk.team_pick_result==="Win"?"win":"lose";var ticon=pk.team_pick_result==="Win"?"\u2705":"\u274c";html+="<span class=\'result-badge "+tcls+"\'>"+(pk.team_pick_result==="Win"?"\u2705":"\u274c")+"</span>";}
html+="</div>";
}
if(pk.agg_pick){
html+="<div class=\'pick-row\' style=\'opacity:.75;margin-left:16px\'>";
html+="<div><div class=\'pick-info\' style=\'font-size:.9rem\'>\u26a1 "+pk.agg_pick+"</div>";
html+="<div class=\'pick-meta\'>Pick agressif</div></div>";
if(pk.agg_pick_result){var acls=pk.agg_pick_result==="Win"?"win":"lose";html+="<span class=\'result-badge "+acls+"\'>"+(pk.agg_pick_result==="Win"?"\u2705":"\u274c")+"</span>";}
html+="</div>";
}'''

if OLD_SECONDARY_BLOCK in html:
    html = html.replace(OLD_SECONDARY_BLOCK, NEW_SECONDARY_BLOCK, 1)
    print("index.html : pattern principal trouvé et appliqué")
else:
    # Fallback : chercher toutes les variantes du bloc team_pick
    # (selon la version exacte du HTML sur le serveur)
    import re as _re
    pattern = r"if\(pk\.team_pick\)\{[\s\S]*?html\+=\"</div>\";\s*\}\s*if\(pk\.agg_pick\)\{[\s\S]*?html\+=\"</div>\";\s*\}"
    match = _re.search(pattern, html)
    if match:
        print("Pattern alternatif trouvé :")
        print(repr(html[match.start():match.end()]))
        print("→ REMPLACEZ MANUELLEMENT ce bloc par le NEW_SECONDARY_BLOCK ci-dessous:")
        print(repr(NEW_SECONDARY_BLOCK))
    else:
        print("AUCUN pattern team_pick trouvé dans index.html. Contenu autour de 'team_pick':")
        idx = html.find("team_pick")
        if idx >= 0:
            print(repr(html[max(0,idx-100):idx+500]))
        raise AssertionError("Pattern secondaire non trouvé dans index.html")

with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print("index.html OK")

# ─────────────────────────────────────────────────────────────────────────────
# Restart
# ─────────────────────────────────────────────────────────────────────────────
import subprocess
subprocess.run(["systemctl", "restart", "telegram-goal-bot"], check=False)
subprocess.run(["systemctl", "restart", "telegram-goal-bot-dashboard"], check=False)
print("Services redémarrés.")
print("Patch complet terminé.")
