with open('/root/telegram-goal-bot/bot.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '''        # Anti-spam : 1 seule alerte par pick (même match + même Over = bloqué)
        total_goals = info["home_goals"] + info["away_goals"]
        pick_key = f"{fixture_id}_over{total_goals}"  # ex: "12345_over2" = Over 2.5
        if not hasattr(check_matches, "_alerted_picks"):
            check_matches._alerted_picks = _load_alerted_picks()

        if pick_key in check_matches._alerted_picks:
            continue'''

new = '''        # Anti-spam : 1 seule alerte par pick (même match + même Over = bloqué)
        total_goals = info["home_goals"] + info["away_goals"]
        pick_key = f"{fixture_id}_over{total_goals}"  # ex: "12345_over2" = Over 2.5
        if not hasattr(check_matches, "_alerted_picks"):
            check_matches._alerted_picks = _load_alerted_picks()

        if pick_key in check_matches._alerted_picks:
            continue

        # Anti-double-alerte : ne pas alerter Over N+1 si le pick Over N vient d'être validé
        # (but recent = win notif vient d'être envoyée, pas besoin d'envoyer une nouvelle alerte)
        fid_str = str(fixture_id)
        if hasattr(check_matches, "_pending_results") and total_goals > 0:
            _skip_alert = False
            for _pk, _pe in check_matches._pending_results.items():
                if (_pe.get("fixture_id") == fid_str
                        and _pe.get("notified_win")
                        and _pe.get("goals_at_alert") == total_goals - 1):
                    _skip_alert = True
                    logger.info("Skip alerte Over %.1f (but recent valide le pick precedent): %s vs %s",
                                total_goals + 0.5, info["home_team"], info["away_team"])
                    break
            if _skip_alert:
                continue'''

assert old in content, "PATTERN NOT FOUND"
content = content.replace(old, new, 1)

with open('/root/telegram-goal-bot/bot.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('OK')
