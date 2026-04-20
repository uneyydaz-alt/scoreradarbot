"""Integration Google Sheets - Log des alertes dans un tableur."""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List

import gspread

from config import GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_FILE

logger = logging.getLogger(__name__)

# Fuseau horaire Paris (UTC+1 / UTC+2 en été)
PARIS_TZ = timezone(timedelta(hours=1))

# Couleurs (format RGB 0-1 pour Google Sheets API)
COLOR_GREEN = {"red": 0.0, "green": 0.8, "blue": 0.0}      # Win
COLOR_RED = {"red": 0.9, "green": 0.0, "blue": 0.0}         # Lose
COLOR_YELLOW = {"red": 1.0, "green": 1.0, "blue": 0.0}      # En cours

# En-têtes du tableau (11 colonnes, A à K)
HEADERS = [
    "DATE", "HEURE", "CHAMPIONNAT", "EQUIPES", "SCORE (alerte)",
    "MINUTE", "PICK", "CONFIANCE", "xG DETTE",
    "RESULTAT"
]

_client = None
_sheet = None


def _get_sheet():
    """Initialise et retourne la feuille Google Sheets."""
    global _client, _sheet

    if _sheet is not None:
        return _sheet

    if not GOOGLE_SHEET_ID or not GOOGLE_CREDENTIALS_FILE:
        logger.warning("Google Sheets non configure (GOOGLE_SHEET_ID ou GOOGLE_CREDENTIALS_FILE manquant)")
        return None

    try:
        _client = gspread.service_account(filename=GOOGLE_CREDENTIALS_FILE)
        spreadsheet = _client.open_by_key(GOOGLE_SHEET_ID)
        _sheet = spreadsheet.sheet1

        # Vérifier si les en-têtes existent déjà
        existing = _sheet.row_values(1)
        if not existing or existing[0] != "DATE" or existing[1] != "HEURE":
            _sheet.update("A1", [HEADERS])
            _sheet.format("A1:J1", {
                "textFormat": {"bold": True, "fontSize": 11},
                "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.2},
                "horizontalAlignment": "CENTER",
            })
            _sheet.freeze(rows=1)
            spreadsheet.batch_update({
                "requests": [
                    {"updateDimensionProperties": {
                        "range": {"sheetId": 0, "dimension": "COLUMNS",
                                  "startIndex": i, "endIndex": i + 1},
                        "properties": {"pixelSize": w},
                        "fields": "pixelSize"
                    }}
                    for i, w in enumerate([
                        100, 70, 150, 250, 100, 70, 100, 80, 80, 80
                    ])
                ]
            })
            logger.info("En-tetes Google Sheets crees")

        return _sheet

    except Exception as e:
        logger.error("Erreur connexion Google Sheets: %s", e)
        _sheet = None
        return None


def log_alert(signal, fixture_id=None):
    """Ajoute une ligne d'alerte dans le Google Sheet (ordre chronologique)."""
    sheet = _get_sheet()
    if sheet is None:
        return None

    try:
        now = datetime.now(PARIS_TZ)

        # Extraire les infos du signal
        info = signal.get("fixture_info", {})
        home = info.get("home_team", "?")
        away = info.get("away_team", "?")
        home_goals = info.get("home_goals", 0)
        away_goals = info.get("away_goals", 0)
        elapsed = info.get("elapsed", 0)
        league = info.get("league_name", "?")
        confidence = signal.get("confidence", 0)
        stats = signal.get("stats", {})
        total_xg = stats.get("home_xg", 0) + stats.get("away_xg", 0)
        total_goals = home_goals + away_goals
        xg_debt = total_xg - total_goals

        pick = "Over %.1f" % (total_goals + 0.5)
        team_str = "%s - %s" % (home, away)

        # Picks secondaires (equipe + agressif)
        dominant_team = signal.get("dominant_team", "")
        dominant_side = signal.get("dominant_side", "home")
        dom_goals = home_goals if dominant_side == "home" else away_goals
        team_pick = "Over %.1f %s" % (dom_goals + 0.5, dominant_team) if dominant_team else ""
        agg_pick = ("Prochain but — %s" % dominant_team) if dominant_team else ""

        row = [
            now.strftime("%d/%m/%Y"),
            now.strftime("%H:%M"),
            league,
            team_str,
            "%d - %d" % (home_goals, away_goals),
            "%d'" % elapsed,
            pick,
            "%d%%" % confidence,
            "%.2f" % xg_debt,
            "En cours",
            team_pick,
            agg_pick,
        ]

        # Ajouter en bas (tri chronologique naturel)
        sheet.append_row(row, value_input_option="USER_ENTERED")
        row_num = len(sheet.get_all_values())
        logger.info("Google Sheets: alerte ajoutee ligne %d (%s, pick %s)",
                     row_num, team_str, pick)

        # Colorer la ligne en jaune (en cours)
        sheet.format("A%d:J%d" % (row_num, row_num), {
            "backgroundColor": COLOR_YELLOW,
        })

        return row_num

    except Exception as e:
        logger.error("Erreur ajout Google Sheets: %s", e)
        global _sheet
        _sheet = None
        return None


def get_pending_rows():
    """Retourne les lignes 'En cours' du sheet avec leurs infos.

    Returns:
        Liste de dicts: [{"row_num": 5, "teams": "A - B", "score_at_alert": "1 - 0", "pick": "Over 1.5"}, ...]
    """
    sheet = _get_sheet()
    if sheet is None:
        return []

    try:
        rows = sheet.get_all_values()
        pending = []
        for i, r in enumerate(rows):
            if i == 0:
                continue
            if len(r) >= 10 and r[9] == "En cours":
                pending.append({
                    "row_num": i + 1,
                    "teams": r[3] if len(r) > 3 else "",
                    "score_at_alert": r[4] if len(r) > 4 else "",
                    "pick": r[6] if len(r) > 6 else "",
                })
        return pending
    except Exception as e:
        logger.error("Erreur lecture pending rows: %s", e)
        return []


def finalize_row(row_num, current_goals):
    """Finalise une ligne: Win (vert) ou Lose (rouge) selon le score actuel."""
    sheet = _get_sheet()
    if sheet is None:
        return

    try:
        score_cell = sheet.cell(row_num, 5).value
        if score_cell and " - " in score_cell:
            parts = score_cell.split(" - ")
            goals_at_alert = int(parts[0].strip()) + int(parts[1].strip())
        else:
            goals_at_alert = 0

        goal_after = current_goals > goals_at_alert
        result = "Win" if goal_after else "Lose"
        color = COLOR_GREEN if goal_after else COLOR_RED

        sheet.update("J%d" % row_num, [[result]])
        sheet.format("A%d:J%d" % (row_num, row_num), {
            "backgroundColor": color,
        })
        logger.info("Google Sheets: ligne %d -> %s (buts: %d vs %d à l'alerte)",
                     row_num, result, current_goals, goals_at_alert)

    except Exception as e:
        logger.error("Erreur finalisation ligne %d: %s", row_num, e)


def update_live_colors(row_nums, current_goals):
    """Colore en vert les picks déjà validés pendant le match (live)."""
    sheet = _get_sheet()
    if sheet is None:
        return

    if isinstance(row_nums, int):
        row_nums = [row_nums]

    try:
        for row_num in row_nums:
            try:
                # Vérifier si déjà finalisé (Win/Lose)
                resultat = sheet.cell(row_num, 10).value  # Colonne K = RESULTAT
                if resultat in ("Win", "Lose"):
                    continue

                score_cell = sheet.cell(row_num, 5).value  # Colonne E = SCORE (alerte)
                if score_cell and " - " in score_cell:
                    parts = score_cell.split(" - ")
                    goals_at_alert = int(parts[0].strip()) + int(parts[1].strip())
                else:
                    goals_at_alert = 0

                if current_goals > goals_at_alert:
                    # Pick validé en live → vert
                    sheet.format("A%d:J%d" % (row_num, row_num), {
                        "backgroundColor": COLOR_GREEN,
                    })
                    sheet.update("J%d" % row_num, [["Win ✓"]])
                    logger.info("Google Sheets: ligne %d -> Win live (buts: %d > %d)",
                                row_num, current_goals, goals_at_alert)

            except Exception as e:
                logger.error("Erreur update live ligne %d: %s", row_num, e)

    except Exception as e:
        logger.error("Erreur update live colors: %s", e)


def update_result(row_nums, final_score_str, final_goals, fixture_id=None, team_pick_win=None):
    """Met à jour le résultat final de toutes les alertes d'un match."""
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

                sheet.update("J%d" % row_num, [[result]])

                # Résultat des picks secondaires (equipe + agressif)
                if team_pick_win is not None:
                    tp_result = "Win" if team_pick_win else "Lose"
                    sheet.update("M%d" % row_num, [[tp_result, tp_result]])  # M=team_pick_result, N=agg_pick_result

                sheet.format("A%d:N%d" % (row_num, row_num), {
                    "backgroundColor": color,
                })

                logger.info("Google Sheets: ligne %d -> %s (score: %s)", row_num, result, final_score_str)

            except Exception as e:
                logger.error("Erreur update ligne %d: %s", row_num, e)

    except Exception as e:
        logger.error("Erreur mise a jour Google Sheets: %s", e)
        global _sheet
        _sheet = None


def update_chart_data():
    """Met a jour les donnees, KPIs et le graphique Profit."""
    try:
        sheet = _get_sheet()
        if sheet is None:
            return

        sp = sheet.spreadsheet
        try:
            stats_ws = sp.worksheet("Stats")
        except Exception:
            return

        main_sheet_id = sheet.id
        stats_sheet_id = stats_ws.id

        rows = sheet.get_all_values()
        wins = 0
        losses = 0
        total_staked = 0.0
        profit = 0.0
        chart_data = [["#", "Profit (u)"]]
        bet_num = 0

        def _extract_stake(pick_str):
            import re
            m = re.search(r"(\d+\.?\d*)\s*[Ff]", pick_str)
            if m:
                return float(m.group(1))
            return 0.5

        for r in rows[1:]:
            res = r[9] if len(r) >= 10 else ""
            pick = r[6] if len(r) >= 7 else ""
            stake = _extract_stake(pick)
            if "Win" in res:
                wins += 1
                bet_num += 1
                total_staked += stake
                profit += stake
            elif "Lose" in res:
                losses += 1
                bet_num += 1
                total_staked += stake
                profit -= stake
            else:
                continue
            chart_data.append([bet_num, round(profit, 2)])

        total = wins + losses
        pct = int(wins / total * 100) if total > 0 else 0
        roi = round(profit / total_staked * 100, 1) if total_staked > 0 else 0.0

        stats_ws.clear()
        stats_ws.update(range_name="A1", values=chart_data, value_input_option="RAW")

        # Calculate streak
        streak = 0
        streak_type = ""
        for r in reversed(rows[1:]):
            res = r[9] if len(r) >= 10 else ""
            if "Win" in res:
                if streak_type == "" or streak_type == "W":
                    streak += 1
                    streak_type = "W"
                else:
                    break
            elif "Lose" in res:
                if streak_type == "" or streak_type == "L":
                    streak += 1
                    streak_type = "L"
                else:
                    break
            # Skip "En cours" rows
        streak_str = "%d%s" % (streak, streak_type)

        kpi_data = [
            ["PARIS", "WINRATE", "ROI", "STREAK"],
            [total, str(pct) + "%", str(roi) + "%", streak_str],
        ]
        sheet.update(range_name="L1", values=kpi_data, value_input_option="RAW")
        sheet.batch_clear(["P1:Q25"])

        data_rows = len(chart_data)
        requests = []

        # Dark background L1:N22
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": main_sheet_id,
                    "startRowIndex": 0, "endRowIndex": 22,
                    "startColumnIndex": 11, "endColumnIndex": 15
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.08, "green": 0.09, "blue": 0.12}
                    }
                },
                "fields": "userEnteredFormat.backgroundColor"
            }
        })

        # KPI headers L1:N1
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": main_sheet_id,
                    "startRowIndex": 0, "endRowIndex": 1,
                    "startColumnIndex": 11, "endColumnIndex": 15
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.08, "green": 0.09, "blue": 0.12},
                        "textFormat": {
                            "bold": True,
                            "fontSize": 9,
                            "foregroundColor": {"red": 0.45, "green": 0.45, "blue": 0.5}
                        },
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "BOTTOM"
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
            }
        })

        # KPI values L2:N2
        val_color = {"red": 0.3, "green": 0.9, "blue": 0.6}
        if roi < 0:
            val_color = {"red": 0.95, "green": 0.3, "blue": 0.3}

        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": main_sheet_id,
                    "startRowIndex": 1, "endRowIndex": 2,
                    "startColumnIndex": 11, "endColumnIndex": 15
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.08, "green": 0.09, "blue": 0.12},
                        "textFormat": {
                            "bold": True,
                            "fontSize": 11,
                            "foregroundColor": val_color
                        },
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "TOP"
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
            }
        })

        # Column widths L M N = 120px each
        for col_idx in range(11, 15):
            requests.append({
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": main_sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": col_idx,
                        "endIndex": col_idx + 1
                    },
                    "properties": {"pixelSize": 120},
                    "fields": "pixelSize"
                }
            })

        # Clear all borders in dashboard area
        requests.append({
            "updateBorders": {
                "range": {
                    "sheetId": main_sheet_id,
                    "startRowIndex": 0, "endRowIndex": 22,
                    "startColumnIndex": 11, "endColumnIndex": 15
                },
                "top": {"style": "NONE"},
                "bottom": {"style": "NONE"},
                "left": {"style": "NONE"},
                "right": {"style": "NONE"},
                "innerHorizontal": {"style": "NONE"},
                "innerVertical": {"style": "NONE"}
            }
        })

        # Delete old charts
        metadata = sp.fetch_sheet_metadata()
        for s in metadata.get("sheets", []):
            for c in s.get("charts", []):
                requests.append({"deleteEmbeddedObject": {"objectId": c["chartId"]}})

        # Line chart anchored at L3
        line_color = {"red": 0.3, "green": 0.9, "blue": 0.6}
        if profit < 0:
            line_color = {"red": 0.95, "green": 0.3, "blue": 0.3}

        requests.append({
            "addChart": {
                "chart": {
                    "spec": {
                        "title": "PROGRESSION",
                        "titleTextFormat": {
                            "bold": True,
                            "fontSize": 9,
                            "foregroundColor": {"red": 0.45, "green": 0.45, "blue": 0.5}
                        },
                        "backgroundColor": {"red": 0.08, "green": 0.09, "blue": 0.12},
                        "basicChart": {
                            "chartType": "LINE",
                            "legendPosition": "NO_LEGEND",
                            "lineSmoothing": True,
                            "axis": [
                                {
                                    "position": "BOTTOM_AXIS",
                                    "title": "",
                                    "format": {
                                        "fontFamily": "Roboto",
                                        "fontSize": 9,
                                        "foregroundColor": {"red": 0.6, "green": 0.6, "blue": 0.65}
                                    }
                                },
                                {
                                    "position": "LEFT_AXIS",
                                    "title": "",
                                    "format": {
                                        "fontFamily": "Roboto",
                                        "fontSize": 9,
                                        "foregroundColor": {"red": 0.6, "green": 0.6, "blue": 0.65}
                                    }
                                }
                            ],
                            "domains": [{
                                "domain": {
                                    "sourceRange": {
                                        "sources": [{
                                            "sheetId": stats_sheet_id,
                                            "startRowIndex": 0,
                                            "endRowIndex": data_rows,
                                            "startColumnIndex": 0,
                                            "endColumnIndex": 1
                                        }]
                                    }
                                }
                            }],
                            "series": [{
                                "series": {
                                    "sourceRange": {
                                        "sources": [{
                                            "sheetId": stats_sheet_id,
                                            "startRowIndex": 0,
                                            "endRowIndex": data_rows,
                                            "startColumnIndex": 1,
                                            "endColumnIndex": 2
                                        }]
                                    }
                                },
                                "targetAxis": "LEFT_AXIS",
                                "color": line_color,
                                "lineStyle": {"width": 3}
                            }]
                        }
                    },
                    "position": {
                        "overlayPosition": {
                            "anchorCell": {
                                "sheetId": main_sheet_id,
                                "rowIndex": 2,
                                "columnIndex": 11
                            },
                            "widthPixels": 480,
                            "heightPixels": 400
                        }
                    }
                }
            }
        })

        sp.batch_update({"requests": requests})
        logger.info("Dashboard updated: %d paris, winrate %d%%, ROI %.1f%%", total, pct, roi)
    except Exception as e:
        logger.error("Erreur update chart: %s", e)


def get_all_rows():
    """Retourne toutes les lignes du sheet principal (sans header)."""
    ws = _get_sheet()
    
    return ws.get_all_values()[1:]  # Skip header


def get_week_results():
    """Retourne les resultats de la semaine en cours."""
    from datetime import datetime, timedelta
    ws = _get_sheet()
    
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return []

    header = rows[0]
    data_rows = rows[1:]

    # Trouver les indices des colonnes
    col_map = {}
    for i, h in enumerate(header):
        h_lower = h.strip().lower()
        if "date" in h_lower:
            col_map["date"] = i
        elif "equipe" in h_lower or "teams" in h_lower:
            col_map["teams"] = i
        elif "pick" in h_lower:
            col_map["pick"] = i
        elif "confiance" in h_lower or "conf" in h_lower:
            col_map["confidence"] = i
        elif "score" in h_lower:
            col_map["score"] = i
        elif "resultat" in h_lower or "result" in h_lower:
            col_map["result"] = i
        elif "championnat" in h_lower or "league" in h_lower:
            col_map["league"] = i
        elif "minute" in h_lower:
            col_map["minute"] = i

    # Filtrer sur la semaine en cours (lundi a dimanche)
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    monday_str = monday.strftime("%d/%m/%Y")

    results = []
    for row in data_rows:
        if len(row) <= max(col_map.values(), default=0):
            continue

        date_str = row[col_map.get("date", 0)].strip()
        if not date_str:
            continue

        # Parser la date (format DD/MM/YYYY)
        try:
            row_date = datetime.strptime(date_str, "%d/%m/%Y")
        except ValueError:
            try:
                row_date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue

        if row_date < monday:
            continue

        result_val = row[col_map.get("result", -1)].strip() if "result" in col_map else ""

        conf_str = row[col_map.get("confidence", -1)].strip() if "confidence" in col_map else "0"
        try:
            conf = int(float(conf_str))
        except (ValueError, TypeError):
            conf = 0

        # Parse score for home/away goals
        score_str = row[col_map.get("score", -1)].strip() if "score" in col_map else "0 - 0"
        score_parts = score_str.split(" - ") if " - " in score_str else score_str.split("-")
        h_goals = score_parts[0].strip() if len(score_parts) >= 1 else "0"
        a_goals = score_parts[1].strip() if len(score_parts) >= 2 else "0"

        teams_str = row[col_map.get("teams", -1)].strip() if "teams" in col_map else "?"
        team_parts = teams_str.split(" - ") if " - " in teams_str else [teams_str, ""]

        results.append({
            "date": date_str,
            "teams": teams_str,
            "home": team_parts[0].strip(),
            "away": team_parts[1].strip() if len(team_parts) > 1 else "",
            "home_goals": h_goals,
            "away_goals": a_goals,
            "league": row[col_map.get("league", -1)].strip() if "league" in col_map else "Autre",
            "pick": row[col_map.get("pick", -1)].strip() if "pick" in col_map else "?",
            "confidence": conf,
            "score": score_str,
            "minute": row[col_map.get("minute", -1)].strip() if "minute" in col_map else "",
            "result": result_val,
        })

    return results
