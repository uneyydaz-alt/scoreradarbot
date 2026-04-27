"""Value Radar Bot — Détection de value bets pré-match via Pinnacle."""

import logging
from datetime import datetime, timezone, timedelta, time as dt_time
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import (
    VALUE_BOT_TOKEN, ADMIN_CHAT_ID, MIN_EDGE,
    LIVE_SPORTS, DIGEST_SPORTS,
)
from odds_client import fetch_schedule_and_bets, fetch_sport_value_bets, fetch_value_bets, fetch_scores, quota_remaining
from tracker import filter_new, mark_all_sent, mark_sent, save_digest, load_digest

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
PARIS = ZoneInfo("Europe/Paris")


# ── Formatage ─────────────────────────────────────────────────────────────────

def _fmt_alert(vb: dict, label: str = "") -> str:
    try:
        ko = datetime.fromisoformat(vb["kickoff"].replace("Z", "+00:00"))
        ko_str = ko.astimezone(PARIS).strftime("%d/%m %H:%M")
    except Exception:
        ko_str = "?"
    edge = vb["edge"]
    icon = "🔥" if edge >= 7 else "✅"
    header = f"📡 VALUE BET {label}{icon}\n\n" if label else f"📡 VALUE BET {icon}\n\n"
    return (
        f"{header}"
        f"⚽ {vb['home']} vs {vb['away']}\n"
        f"🏆 {vb['league']} — {ko_str}\n\n"
        f"• Marché : {vb['market']}\n"
        f"• Cote : {vb['soft_odds']} ({vb['bookmaker']})\n"
        f"• Prob implicite : {vb['implied_prob']}%\n"
        f"• Prob réelle : {vb['true_prob']}%\n"
        f"• Range : {vb['odds_low']} – {vb['odds_high']}\n\n"
        f"• Edge : +{edge}%\n"
        f"• Décision : BET\n\n"
        f"⚠️ Le long terme se construit sur la répétition d'edges positifs."
    )


def _fmt_digest(vbs: list) -> str:
    day = datetime.now(PARIS).strftime("%A %d/%m").capitalize()
    lines = [f"📊 Value Bets — {day}\n"]
    for i, vb in enumerate(vbs, 1):
        try:
            ko = datetime.fromisoformat(vb["kickoff"].replace("Z", "+00:00"))
            ko_str = ko.astimezone(PARIS).strftime("%H:%M")
        except Exception:
            ko_str = "?"
        icon = "🔥" if vb["edge"] >= 7 else "✅"
        lines.append(
            f"{i}. {vb['home']} vs {vb['away']} — {ko_str}\n"
            f"   {vb['market']} • {vb['soft_odds']} ({vb['bookmaker']})\n"
            f"   Prob réelle {vb['true_prob']}% vs implicite {vb['implied_prob']}% • +{vb['edge']}% {icon}"
        )
    rem = quota_remaining()
    footer = f"\n📌 {len(vbs)} opportunité(s)"
    if rem is not None:
        footer += f" • Quota restant : {rem} req"
    footer += "\n⚠️ Probabilités via Pinnacle. Jouez de manière responsable."
    lines.append(footer)
    return "\n\n".join(lines)


async def _send(bot, text: str, reply_to: int = None):
    return await bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=text,
        reply_to_message_id=reply_to,
    )


# ── Jobs dynamiques ────────────────────────────────────────────────────────────

async def job_targeted_check(context: ContextTypes.DEFAULT_TYPE):
    """Check ciblé avant KO ou à la MT sur un sport précis."""
    data  = context.job.data
    sport = data["sport"]
    label = data.get("label", "")

    vbs     = await fetch_sport_value_bets(sport, min_edge=MIN_EDGE)
    new_vbs = filter_new(vbs)

    if not new_vbs:
        logger.info("Check ciblé [%s] %s : aucun nouveau value bet", sport, label)
        return

    for vb in new_vbs:
        await _send(context.bot, _fmt_alert(vb, label))
        mark_sent(vb["id"])
        logger.info("Alert [%s] %s : %s vs %s — %s (+%.1f%%)",
                    label, sport, vb["home"], vb["away"], vb["market"], vb["edge"])


def _schedule_match_jobs(jq, schedule: list, now: datetime):
    """Programme un check KO-5min et un check MT pour chaque match."""
    count = 0
    for match in schedule:
        ko   = match["kickoff"]
        pre  = ko - timedelta(minutes=5)
        half = ko + timedelta(minutes=50)

        if pre > now:
            jq.run_once(
                job_targeted_check,
                when=pre,
                data={"sport": match["sport"], "label": "PRÉ-MATCH "},
                name=f"pre_{match['home']}_{match['away']}",
            )
            count += 1

        if half > now:
            jq.run_once(
                job_targeted_check,
                when=half,
                data={"sport": match["sport"], "label": "MI-TEMPS "},
                name=f"ht_{match['home']}_{match['away']}",
            )
            count += 1

    logger.info("%d jobs dynamiques programmés pour %d matchs", count, len(schedule))
    return count


# ── Job matin ─────────────────────────────────────────────────────────────────

async def job_morning_scan(context: ContextTypes.DEFAULT_TYPE):
    """
    Scan du matin (sam + dim) :
    1. Fetch digest + planning des matchs (1 seul lot de requêtes API)
    2. Envoie le digest value bets
    3. Programme les checks KO-5min et MT pour chaque match du jour
    """
    now = datetime.now(timezone.utc)
    result = await fetch_schedule_and_bets(DIGEST_SPORTS, hours_ahead=36, min_edge=MIN_EDGE)

    vbs      = result["bets"]
    schedule = result["schedule"]

    # Digest
    if vbs:
        top = vbs[:10]
        msg = await _send(context.bot, _fmt_digest(top))
        mark_all_sent(top)
        save_digest(msg.message_id, ADMIN_CHAT_ID, top)
    else:
        await _send(context.bot, f"📊 Aucun value bet détecté ce matin (edge ≥ {MIN_EDGE*100:.0f}%)")

    # Jobs dynamiques
    nb_jobs = _schedule_match_jobs(context.job_queue, schedule, now)
    await _send(
        context.bot,
        f"⏱ {len(schedule)} match(s) programmé(s) aujourd'hui\n"
        f"→ {nb_jobs} checks automatiques (KO-5min + MT) planifiés"
    )


# ── Validation soir ───────────────────────────────────────────────────────────

def _validate_bet(vb: dict, scores: list) -> str | None:
    """Retourne ✅ ou ❌ si le match est terminé, None sinon."""
    for match in scores:
        if not match.get("completed"):
            continue
        if match["home_team"] != vb["home"] or match["away_team"] != vb["away"]:
            continue
        match_scores = match.get("scores") or []
        if len(match_scores) < 2:
            continue
        score_map  = {s["name"]: int(s["score"]) for s in match_scores}
        home_score = score_map.get(vb["home"], 0)
        away_score = score_map.get(vb["away"], 0)
        total      = home_score + away_score
        market     = vb["market"]
        if market.startswith("1X2 — "):
            outcome = market.replace("1X2 — ", "")
            if outcome == vb["home"]:
                won = home_score > away_score
            elif outcome == vb["away"]:
                won = away_score > home_score
            else:
                won = home_score == away_score
            return "✅" if won else "❌"
        elif market.startswith("Over "):
            return "✅" if total > float(market.split()[1]) else "❌"
        elif market.startswith("Under "):
            return "✅" if total < float(market.split()[1]) else "❌"
    return None


async def job_evening_validation(context: ContextTypes.DEFAULT_TYPE):
    """Valide les paris du matin et reply au digest avec les résultats."""
    state = load_digest()
    if not state:
        logger.info("Validation soir : pas de digest aujourd'hui")
        return

    scores = await fetch_scores(DIGEST_SPORTS)
    if not scores:
        logger.info("Validation soir : aucun résultat disponible")
        return

    bets  = state["bets"]
    lines = ["📊 Résultats du jour\n"]
    nb_validated = 0

    for vb in bets:
        result = _validate_bet(vb, scores)
        if result:
            nb_validated += 1
            lines.append(f"{result} {vb['home']} vs {vb['away']} — {vb['market']}")
        else:
            lines.append(f"⏳ {vb['home']} vs {vb['away']} — résultat non disponible")

    if nb_validated == 0:
        logger.info("Validation soir : aucun match terminé trouvé")
        return

    await _send(context.bot, "\n".join(lines), reply_to=state["message_id"])
    logger.info("Validation soir envoyée : %d/%d matchs validés", nb_validated, len(bets))


# ── Commands ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📡 Value Radar Bot\n\n"
        "Détection de value bets pré-match & live.\n\n"
        "/value — Check value bets à venir (24h)\n"
        "/live — Check matchs en cours maintenant\n"
        "/digest — Digest complet + programme les checks du jour\n"
        "/sports — Compétitions surveillées\n"
        "/quota — Quota API restant\n"
        "/status — Statut"
    )


async def cmd_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Recherche en cours...")
    vbs     = await fetch_value_bets(LIVE_SPORTS, hours_ahead=24, min_edge=MIN_EDGE)
    new_vbs = filter_new(vbs)
    if not new_vbs:
        msg = f"Aucun nouveau value bet (edge ≥ {MIN_EDGE*100:.0f}%)"
        if vbs:
            msg += f"\n({len(vbs)} trouvé(s) déjà envoyé(s) aujourd'hui)"
        await update.message.reply_text(msg)
        return
    for vb in new_vbs[:5]:
        await update.message.reply_text(_fmt_alert(vb))
        mark_sent(vb["id"])


async def cmd_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Génération du digest + programmation des checks...")
    now    = datetime.now(timezone.utc)
    result = await fetch_schedule_and_bets(DIGEST_SPORTS, hours_ahead=36, min_edge=MIN_EDGE)
    vbs      = result["bets"]
    schedule = result["schedule"]
    if not vbs:
        await _send(context.bot, f"📊 Aucun value bet détecté (edge ≥ {MIN_EDGE*100:.0f}%)")
        await update.message.reply_text("Aucun value bet détecté.")
    else:
        top = vbs[:10]
        msg = await _send(context.bot, _fmt_digest(top))
        mark_all_sent(top)
        save_digest(msg.message_id, ADMIN_CHAT_ID, top)
        await update.message.reply_text(f"✅ Digest envoyé dans le canal ({len(top)} value bets)")
    nb_jobs = _schedule_match_jobs(context.job_queue, schedule, now)
    await update.message.reply_text(
        f"✅ {len(schedule)} match(s) | {nb_jobs} checks programmés (KO-5min + MT)"
    )


async def cmd_quota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rem = quota_remaining()
    if not rem:
        await update.message.reply_text("Quota inconnu — aucun appel depuis le démarrage.")
        return
    lines = ["📊 Quota The Odds API\n"]
    for label, val in rem.items():
        lines.append(f"• {label} : {val} req restantes")
    await update.message.reply_text("\n".join(lines))


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(PARIS)
    jobs = context.job_queue.jobs()
    dynamic = [j for j in jobs if j.name and (j.name.startswith("pre_") or j.name.startswith("ht_"))]
    await update.message.reply_text(
        f"📡 Value Radar Bot\n"
        f"• Heure : {now.strftime('%d/%m %H:%M')} Paris\n"
        f"• Checks dynamiques en attente : {len(dynamic)}\n"
        f"• Edge minimum : {MIN_EDGE*100:.0f}%\n"
        f"• Quota restant : {quota_remaining() or '?'} req"
    )


async def cmd_sports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    live_list  = "\n".join(f"  • {s}" for s in LIVE_SPORTS)
    extra      = [s for s in DIGEST_SPORTS if s not in LIVE_SPORTS]
    extra_list = "\n".join(f"  • {s}" for s in extra)
    await update.message.reply_text(
        f"⚽ Sports surveillés\n\n"
        f"🔴 Live & Digest ({len(LIVE_SPORTS)}) :\n{live_list}\n\n"
        f"📊 Digest uniquement ({len(extra)}) :\n{extra_list}\n\n"
        f"Total : {len(DIGEST_SPORTS)} compétitions"
    )


async def cmd_live(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check value bets sur les matchs actuellement en cours."""
    await update.message.reply_text("🔴 Scan live en cours...")
    from odds_client import _fetch, _analyze, _dedup
    now     = datetime.now(timezone.utc)
    all_vbs = []

    for sport in LIVE_SPORTS:
        for match in await _fetch(sport):
            try:
                ko = datetime.fromisoformat(match["commence_time"].replace("Z", "+00:00"))
                if not (now - timedelta(minutes=110) <= ko <= now):
                    continue
                all_vbs.extend(_analyze(match, MIN_EDGE))
            except Exception as e:
                logger.error("Parse error live [%s]: %s", sport, e)

    unique  = _dedup(all_vbs)
    new_vbs = filter_new(unique)

    if not new_vbs:
        msg = "Aucun value bet live détecté"
        if unique:
            msg += f"\n({len(unique)} trouvé(s) déjà envoyé(s))"
        await update.message.reply_text(msg)
        return

    for vb in new_vbs[:5]:
        await update.message.reply_text(_fmt_alert(vb, "LIVE "))
        mark_sent(vb["id"])


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not VALUE_BOT_TOKEN:
        raise ValueError("VALUE_BOT_TOKEN manquant dans .env")
    if not ADMIN_CHAT_ID:
        raise ValueError("VALUE_BOT_ADMIN_ID manquant dans .env")

    app = Application.builder().token(VALUE_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("value",  cmd_value))
    app.add_handler(CommandHandler("digest", cmd_digest))
    app.add_handler(CommandHandler("quota",  cmd_quota))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("sports", cmd_sports))
    app.add_handler(CommandHandler("live",   cmd_live))

    # Digest matin + programmation des jobs dynamiques : sam + dim à 9h Paris
    app.job_queue.run_daily(
        job_morning_scan,
        time=dt_time(hour=9, minute=0, tzinfo=PARIS),
        days=(5, 6),
    )

    # Validation soir : sam + dim à 23h Paris
    app.job_queue.run_daily(
        job_evening_validation,
        time=dt_time(hour=23, minute=0, tzinfo=PARIS),
        days=(5, 6),
    )

    print("[OK] Value Radar Bot démarré")
    print("     Digest + jobs dynamiques : sam + dim 9h Paris")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
