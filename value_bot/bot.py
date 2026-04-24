"""Value Radar Bot — Détection de value bets pré-match via Pinnacle."""

import logging
from datetime import datetime, timezone, time as dt_time
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import (
    VALUE_BOT_TOKEN, ADMIN_CHAT_ID, MIN_EDGE,
    CHECK_INTERVAL, LIVE_SPORTS, DIGEST_SPORTS,
)
from odds_client import fetch_value_bets, quota_remaining
from tracker import filter_new, mark_all_sent, mark_sent

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

PARIS = ZoneInfo("Europe/Paris")


def _fmt_vb(vb: dict) -> str:
    """Formate un value bet pour une alerte individuelle."""
    try:
        ko = datetime.fromisoformat(vb["kickoff"].replace("Z", "+00:00"))
        ko_str = ko.astimezone(PARIS).strftime("%d/%m %H:%M")
    except Exception:
        ko_str = "?"

    edge = vb["edge"]
    icon = "🔥" if edge >= 7 else "✅"

    return (
        f"📡 VALUE BET DÉTECTÉ {icon}\n\n"
        f"⚽ {vb['home']} vs {vb['away']}\n"
        f"🏆 {vb['league']} — {ko_str}\n\n"
        f"• Marché : {vb['market']}\n"
        f"• Cote : {vb['soft_odds']} ({vb['bookmaker']})\n"
        f"• Probabilité implicite : {vb['implied_prob']}%\n"
        f"• Probabilité réelle : {vb['true_prob']}%\n"
        f"• Range de cote : {vb['odds_low']} – {vb['odds_high']}\n\n"
        f"• Edge : +{edge}%\n"
        f"• Confiance : {'Élevée 🔥' if edge >= 7 else 'Moyenne ✅'}\n"
        f"• Décision : BET\n\n"
        f"⚠️ Le long terme se construit sur la répétition d'edges positifs."
    )


def _fmt_digest(vbs: list) -> str:
    """Formate un digest groupé pour le matin du week-end."""
    day = datetime.now(PARIS).strftime("%A %d/%m").capitalize()
    lines = [f"📊 Value Bets — {day}\n"]

    for i, vb in enumerate(vbs, 1):
        try:
            ko = datetime.fromisoformat(vb["kickoff"].replace("Z", "+00:00"))
            ko_str = ko.astimezone(PARIS).strftime("%H:%M")
        except Exception:
            ko_str = "?"

        edge = vb["edge"]
        icon = "🔥" if edge >= 7 else "✅"
        lines.append(
            f"{i}. {vb['home']} vs {vb['away']} — {ko_str}\n"
            f"   {vb['market']} • {vb['soft_odds']} ({vb['bookmaker']})\n"
            f"   Prob réelle {vb['true_prob']}% vs implicite {vb['implied_prob']}% • +{edge}% {icon}"
        )

    rem = quota_remaining()
    footer = f"\n📌 {len(vbs)} opportunité(s) détectée(s)"
    if rem is not None:
        footer += f" • Quota API restant : {rem}"
    footer += "\n⚠️ Probabilités calculées via Pinnacle. Jouez de manière responsable."
    lines.append(footer)

    return "\n\n".join(lines)


async def _send(bot, text: str):
    """Envoie un message à l'admin."""
    await bot.send_message(chat_id=ADMIN_CHAT_ID, text=text)


# ── Jobs ──────────────────────────────────────────────────────────────────────

async def job_live_check(context: ContextTypes.DEFAULT_TYPE):
    """Vérification live toutes les CHECK_INTERVAL secondes (week-end uniquement)."""
    now = datetime.now(PARIS)
    if now.weekday() not in (5, 6):  # 5=sam, 6=dim
        return

    vbs = await fetch_value_bets(LIVE_SPORTS, hours_ahead=12, min_edge=MIN_EDGE)
    new_vbs = filter_new(vbs)

    for vb in new_vbs:
        await _send(context.bot, _fmt_vb(vb))
        mark_sent(vb["id"])
        logger.info("Alert envoyée : %s vs %s — %s (+%.1f%%)",
                    vb["home"], vb["away"], vb["market"], vb["edge"])


async def job_morning_digest(context: ContextTypes.DEFAULT_TYPE):
    """Digest du matin — samedi et dimanche."""
    vbs = await fetch_value_bets(DIGEST_SPORTS, hours_ahead=36, min_edge=MIN_EDGE)

    if not vbs:
        await _send(context.bot, "📊 Aucun value bet détecté ce matin (edge ≥ {:.0f}%)".format(MIN_EDGE * 100))
        return

    top = vbs[:10]
    await _send(context.bot, _fmt_digest(top))
    mark_all_sent(top)
    logger.info("Digest matin envoyé : %d value bets", len(top))


# ── Commands ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📡 Value Radar Bot\n\n"
        "Détection automatique de value bets pré-match.\n\n"
        "Commandes :\n"
        "/value — Chercher les value bets maintenant\n"
        "/digest — Digest complet (toutes ligues)\n"
        "/quota — Quota API restant\n"
        "/status — Statut du bot"
    )


async def cmd_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Déclenche une recherche live maintenant."""
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return
    await update.message.reply_text("🔍 Recherche en cours...")
    vbs = await fetch_value_bets(LIVE_SPORTS, hours_ahead=24, min_edge=MIN_EDGE)
    new_vbs = filter_new(vbs)

    if not new_vbs:
        msg = f"Aucun nouveau value bet (edge ≥ {MIN_EDGE*100:.0f}%)"
        if vbs:
            msg += f"\n({len(vbs)} trouvé(s) mais déjà envoyé(s) aujourd'hui)"
        await update.message.reply_text(msg)
        return

    for vb in new_vbs[:5]:  # max 5 à la fois
        await update.message.reply_text(_fmt_vb(vb))
        mark_sent(vb["id"])


async def cmd_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Digest complet toutes ligues."""
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return
    await update.message.reply_text("📊 Génération du digest...")
    vbs = await fetch_value_bets(DIGEST_SPORTS, hours_ahead=36, min_edge=MIN_EDGE)
    if not vbs:
        await update.message.reply_text("Aucun value bet détecté.")
        return
    top = vbs[:10]
    await update.message.reply_text(_fmt_digest(top))
    mark_all_sent(top)


async def cmd_quota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rem = quota_remaining()
    if rem is None:
        await update.message.reply_text("Quota inconnu — aucun appel API effectué depuis le démarrage.")
    else:
        await update.message.reply_text(f"📊 Quota The Odds API : {rem} requêtes restantes ce mois.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(PARIS)
    is_weekend = now.weekday() in (5, 6)
    await update.message.reply_text(
        f"📡 Value Radar Bot — actif\n"
        f"• Heure : {now.strftime('%d/%m %H:%M')} Paris\n"
        f"• Mode : {'🟢 Week-end (live actif)' if is_weekend else '⚪ Semaine (live en pause)'}\n"
        f"• Check interval : {CHECK_INTERVAL//60} min\n"
        f"• Edge minimum : {MIN_EDGE*100:.0f}%\n"
        f"• Quota restant : {quota_remaining() or '?'} req"
    )


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

    jq = app.job_queue
    # Live check : toutes les CHECK_INTERVAL secondes (s'auto-désactive en semaine)
    jq.run_repeating(job_live_check, interval=CHECK_INTERVAL, first=30)
    # Digest matin : samedi + dimanche à 9h Paris
    jq.run_daily(job_morning_digest, time=dt_time(hour=9, minute=0, tzinfo=PARIS), days=(5, 6))

    print(f"[OK] Value Radar Bot démarré")
    print(f"     Check interval : {CHECK_INTERVAL//60} min (week-end uniquement)")
    print(f"     Digest : sam + dim 9h Paris")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
