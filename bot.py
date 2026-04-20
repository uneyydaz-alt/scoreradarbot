"""Bot Telegram — Goal Signal Detector."""

import asyncio
import json
import logging
import os
from pathlib import Path

from datetime import datetime, timedelta, timezone
import stripe
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import (
    TELEGRAM_BOT_TOKEN,
    DEFAULT_CONFIDENCE_THRESHOLD,
    CHECK_INTERVAL_SECONDS,
    USERS_FILE,
    POPULAR_LEAGUES,
    CHANNEL_USERNAME,
    CHANNEL_ID,
    GRANDFATHERED_FILE,
    PLANS,
    STRIPE_SECRET_KEY,
    ADMIN_ID,
    REFERRAL_TIERS,
)
from api_football import get_live_fixtures, get_fixture_by_id, get_fixture_statistics, parse_fixture_info, parse_statistics, get_live_odds
from analyzer import analyze_match, format_signal
from google_sheets import log_alert, update_result, update_live_colors, get_pending_rows, finalize_row
from footystats import get_todays_matches, find_match_data, parse_prematch_data
from translations import t, get_lang, LANG_FLAGS, SUPPORTED_LANGS
from twitter_bot import (
    build_daily_recap, build_weekend_teaser, build_weekly_thread,
    post_tweet, post_thread,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- Persistance des picks alertés (survit aux restarts) ---

ALERTED_PICKS_FILE = Path(__file__).parent / "alerted_picks.json"
_TWEET_DATE_FILE = Path(__file__).parent / ".tweet_sent_date"


def _load_alerted_picks() -> set:
    """Charge les picks déjà alertés depuis le fichier."""
    if not ALERTED_PICKS_FILE.exists():
        return set()
    try:
        with open(ALERTED_PICKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data)
    except Exception:
        return set()


def _save_alerted_picks(picks: set):
    """Sauvegarde les picks alertés dans un fichier."""
    try:
        # Garder seulement les 500 derniers
        picks_list = list(picks)[-500:]
        with open(ALERTED_PICKS_FILE, "w", encoding="utf-8") as f:
            json.dump(picks_list, f)
    except Exception as e:
        logger.error("Erreur sauvegarde alerted_picks: %s", e)


# --- Persistance des résultats en attente (survit aux restarts) ---

PENDING_RESULTS_FILE = Path(__file__).parent / "pending_results.json"


def _load_pending_results() -> dict:
    """Charge les résultats en attente depuis le fichier."""
    if not PENDING_RESULTS_FILE.exists():
        return {}
    try:
        with open(PENDING_RESULTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_pending_results(pending: dict):
    """Sauvegarde les résultats en attente."""
    try:
        with open(PENDING_RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(pending, f)
    except Exception as e:
        logger.error("Erreur sauvegarde pending_results: %s", e)


# --- Grandfathered members (jamais kick) ---
# Stocke les usernames ET les user IDs pour couvrir les deux cas

def _load_grandfathered() -> dict:
    """Charge {usernames: [...], user_ids: [...]}"""
    if not Path(GRANDFATHERED_FILE).exists():
        return {"usernames": [], "user_ids": []}
    try:
        with open(GRANDFATHERED_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, list):
                # Migration ancien format (liste d'IDs)
                return {"usernames": [], "user_ids": data}
            return data
    except Exception:
        return {"usernames": [], "user_ids": []}


def _save_grandfathered(data: dict):
    with open(GRANDFATHERED_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _is_grandfathered(user_id: int, username: str = None) -> bool:
    gf = _load_grandfathered()
    if user_id in gf.get("user_ids", []):
        return True
    if username and username.lower().lstrip("@") in [u.lower().lstrip("@") for u in gf.get("usernames", [])]:
        return True
    return False


# --- Stockage utilisateurs (fichier JSON simple) ---

def _load_users() -> dict:
    """Charge les utilisateurs depuis le fichier JSON."""
    if not Path(USERS_FILE).exists():
        return {}
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_users(users: dict) -> None:
    """Sauvegarde les utilisateurs dans le fichier JSON."""
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def _get_user(chat_id: int) -> dict:
    """Récupère ou crée un utilisateur."""
    users = _load_users()
    uid = str(chat_id)
    if uid not in users:
        users[uid] = {
            "active": True,
            "threshold": DEFAULT_CONFIDENCE_THRESHOLD,
            "leagues": list(POPULAR_LEAGUES.keys()),
            "alerted_fixtures": [],
            "plan": None,
            "plan_expires": None,
            "lang": None,
            "referral_code": uid,
            "referred_by": None,
            "referral_count": 0,
            "referral_rewarded": [],
        }
        _save_users(users)
    else:
        # Migration: ajouter les champs referral si absents
        changed = False
        if "referral_code" not in users[uid]:
            users[uid]["referral_code"] = uid
            changed = True
        if "referred_by" not in users[uid]:
            users[uid]["referred_by"] = None
            changed = True
        if "referral_count" not in users[uid]:
            users[uid]["referral_count"] = 0
            changed = True
        if "referral_rewarded" not in users[uid]:
            users[uid]["referral_rewarded"] = []
            changed = True
        if changed:
            _save_users(users)
    return users[uid]


def _update_user(chat_id: int, data: dict) -> None:
    """Met à jour les données d'un utilisateur."""
    users = _load_users()
    uid = str(chat_id)
    if uid in users:
        users[uid].update(data)
        _save_users(users)


# --- Helpers abonnement ---

def _user_has_active_plan(user: dict) -> bool:
    plan = user.get("plan")
    if not plan:
        return False
    if plan == "lifetime":
        return True
    expires = user.get("plan_expires")
    if not expires:
        return False
    return datetime.now(timezone.utc).isoformat() < expires


def _plan_expiry_str(user: dict, lang: str = "fr") -> str:
    if user.get("plan") == "lifetime":
        return t("expires_never", lang)
    expires = user.get("plan_expires")
    if not expires:
        return "—"
    dt = datetime.fromisoformat(expires)
    return dt.strftime("%d/%m/%Y %H:%M")


async def _grant_channel_access(bot, chat_id: int):
    if not CHANNEL_ID:
        return None
    try:
        link = await bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
            name=f"user_{chat_id}",
        )
        return link.invite_link
    except Exception as e:
        logger.error("Erreur creation invite link: %s", e)
        return None


async def _kick_from_channel(bot, user_id: int):
    if not CHANNEL_ID:
        return
    # Vérifier si grandfathered (par ID ou username)
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        username = member.user.username if member.user else None
    except Exception:
        username = None
    if _is_grandfathered(user_id, username):
        logger.info("User %d (@%s) est grandfathered, pas de kick", user_id, username)
        return
    try:
        await bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        await bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        logger.info("Kick canal: user %d", user_id)
    except Exception as e:
        logger.error("Erreur kick canal user %d: %s", user_id, e)


# --- Commandes du bot ---

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start — Affiche les plans d'abonnement."""
    chat_id = update.effective_chat.id
    user = _get_user(chat_id)
    _update_user(chat_id, {"active": True})
    tg_lang = update.effective_user.language_code if update.effective_user else None
    lang = get_lang(user, tg_lang)

    # Gerer les liens de parrainage: /start ref_XXXXX
    if context.args and context.args[0].startswith("ref_"):
        ref_code = context.args[0].replace("ref_", "")
        if ref_code != str(chat_id) and not user.get("referred_by"):
            _update_user(chat_id, {"referred_by": ref_code})
            logger.info("User %d referred by %s", chat_id, ref_code)

    if _user_has_active_plan(user):
        plan_name = PLANS.get(user["plan"], {}).get("name", user["plan"])
        await update.message.reply_text(
            f"{t('start_title', lang)}\n\n"
            f"{t('active_sub', lang, plan=plan_name, expires=_plan_expiry_str(user, lang))}\n\n"
            f"/status — /live — /lang",
            parse_mode="Markdown",
        )
        return

    keyboard = [
        [InlineKeyboardButton(t("btn_trial", lang), callback_data="plan_trial")],
        [InlineKeyboardButton(t("btn_monthly", lang), callback_data="plan_monthly")],
        [InlineKeyboardButton(t("btn_semestrial", lang), callback_data="plan_semestrial")],
        [InlineKeyboardButton(t("btn_lifetime", lang), callback_data="plan_lifetime")],
    ]

    await update.message.reply_text(
        f"{t('start_title', lang)}\n"
        f"\n"
        f"{t('start_separator', lang)}\n"
        f"\n"
        f"{t('start_desc', lang)}\n"
        f"\n"
        f"{t('choose_plan', lang)}\n"
        f"\n"
        f"{t('plan_trial', lang)}\n"
        f"{t('plan_monthly', lang)}\n"
        f"{t('plan_semestrial', lang)}\n"
        f"{t('plan_lifetime', lang)}\n"
        f"\n"
        f"🤝 /referral — {t('referral_short', lang)}\n"
        f"🌍 /lang — {t('lang_short', lang)}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def callback_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gere les clics sur les boutons de plan."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    user = _get_user(chat_id)
    tg_lang = query.from_user.language_code if query.from_user else None
    lang = get_lang(user, tg_lang)
    plan_key = query.data.replace("plan_", "")

    if plan_key not in PLANS:
        return

    plan = PLANS[plan_key]

    # Essai gratuit : activer directement
    if plan_key == "trial":
        if user.get("trial_used") or user.get("plan"):
            await query.edit_message_text(t("trial_already_used", lang))
            return
        _update_user(chat_id, {"plan": "trial", "plan_expires": expires, "trial_used": True})
        invite_link = await _grant_channel_access(context.bot, chat_id)
        msg = t("trial_activated", lang) + "\n\n"
        if invite_link:
            msg += f"{t('join_channel', lang)}\n{invite_link}\n\n"
        msg += t("enjoy", lang)
        await query.edit_message_text(msg, parse_mode="Markdown")
        return

    # Plans payants : proposer Stripe ou Stars
    stars = plan.get("stars", 0)
    keyboard = [
        [InlineKeyboardButton(f"💳 {t('pay_card', lang)} — {plan['price'] / 100:.2f} EUR", callback_data=f"stripe_{plan_key}")],
        [InlineKeyboardButton(f"⭐ {t('pay_stars', lang)} — {stars} Stars", callback_data=f"stars_{plan_key}")],
    ]
    await query.edit_message_text(
        f"*{plan['name']}*\n\n{t('choose_payment', lang)}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def callback_stripe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Paiement par carte Stripe."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    user = _get_user(chat_id)
    tg_lang = query.from_user.language_code if query.from_user else None
    lang = get_lang(user, tg_lang)
    plan_key = query.data.replace("stripe_", "")

    if plan_key not in PLANS:
        return

    plan = PLANS[plan_key]

    if not STRIPE_SECRET_KEY:
        await query.edit_message_text(t("payment_not_configured", lang))
        return

    try:
        stripe.api_key = STRIPE_SECRET_KEY
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": f"ScoreRadar — {plan['name']}"},
                    "unit_amount": plan["price"],
                },
                "quantity": 1,
            }],
            mode="payment",
            client_reference_id=f"{chat_id}_{plan_key}",
            success_url="https://t.me/ScoreRadarFR_Bot?start=paid",
            cancel_url="https://t.me/ScoreRadarFR_Bot?start=cancel",
        )
        keyboard = [[InlineKeyboardButton(t("pay_now", lang), url=session.url)]]
        await query.edit_message_text(
            f"*{plan['name']}* — {plan['price'] / 100:.2f} EUR\n\n"
            f"{t('click_to_pay', lang)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Erreur Stripe Checkout: %s", e)
        await query.edit_message_text(t("payment_error", lang))


async def callback_stars(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Paiement par Telegram Stars."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    user = _get_user(chat_id)
    tg_lang = query.from_user.language_code if query.from_user else None
    lang = get_lang(user, tg_lang)
    plan_key = query.data.replace("stars_", "")

    if plan_key not in PLANS:
        return

    plan = PLANS[plan_key]
    stars = plan.get("stars", 0)

    if stars <= 0:
        return

    try:
        await context.bot.send_invoice(
            chat_id=chat_id,
            title=f"ScoreRadar — {plan['name']}",
            description=t("stars_invoice_desc", lang, plan=plan['name']),
            payload=f"{chat_id}_{plan_key}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=plan['name'], amount=stars)],
        )
    except Exception as e:
        logger.error("Erreur Stars invoice: %s", e)
        await query.edit_message_text(t("payment_error", lang))


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Repond au PreCheckoutQuery pour Telegram Stars."""
    query = update.pre_checkout_query
    await query.answer(ok=True)


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gere le paiement Stars reussi."""
    payment = update.message.successful_payment
    payload = payment.invoice_payload

    if "_" not in payload:
        return

    parts = payload.split("_", 1)
    chat_id = int(parts[0])
    plan_key = parts[1]

    if plan_key not in PLANS:
        return

    plan = PLANS[plan_key]
    user = _get_user(chat_id)
    tg_lang = update.effective_user.language_code if update.effective_user else None
    lang = get_lang(user, tg_lang)

    if plan_key == "lifetime":
        _update_user(chat_id, {"plan": "lifetime", "plan_expires": None})
    else:
        expires = (datetime.now(timezone.utc) + timedelta(days=plan["duration_days"])).isoformat()
        _update_user(chat_id, {"plan": plan_key, "plan_expires": expires})

    invite_link = await _grant_channel_access(context.bot, chat_id)

    msg = t("payment_received", lang, plan=plan['name']) + "\n\n"
    if invite_link:
        msg += f"{t('join_channel', lang)}\n{invite_link}\n\n"
    if plan_key == "lifetime":
        msg += t("lifetime_thanks", lang)
    else:
        user = _get_user(chat_id)
        msg += t("expires_on", lang, date=_plan_expiry_str(user, lang))

    await update.message.reply_text(msg, parse_mode="Markdown")
    logger.info("Stars paiement OK: user %d -> plan %s", chat_id, plan_key)

    # Crediter le parrain
    user = _get_user(chat_id)
    referrer = user.get("referred_by")
    if referrer:
        referrer_user = _get_user(int(referrer))
        new_count = referrer_user.get("referral_count", 0) + 1
        _update_user(int(referrer), {"referral_count": new_count})
        await _check_referral_rewards(context.bot, int(referrer))
        logger.info("Referral credit (Stars): user %s -> parrain %s (total: %d)", chat_id, referrer, new_count)


async def cmd_activate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/activate <user_id> <plan> — Admin: activer manuellement un plan."""
    chat_id = update.effective_chat.id
    if chat_id != ADMIN_ID:
        return

    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text("Usage: /activate <user_id> <trial|monthly|semestrial|lifetime>")
        return

    target_id = int(args[0])
    plan_key = args[1]
    if plan_key not in PLANS:
        await update.message.reply_text(f"Plan inconnu: {plan_key}")
        return

    plan = PLANS[plan_key]
    if plan_key == "lifetime":
        _update_user(target_id, {"plan": "lifetime", "plan_expires": None})
    else:
        expires = (datetime.now(timezone.utc) + timedelta(days=plan["duration_days"])).isoformat()
        _update_user(target_id, {"plan": plan_key, "plan_expires": expires})

    invite_link = await _grant_channel_access(context.bot, target_id)
    if invite_link:
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"✅ Ton abonnement *{plan['name']}* a ete active !\n\nRejoins le canal :\n{invite_link}",
                parse_mode="Markdown",
            )
        except Exception:
            pass

    await update.message.reply_text(f"OK — User {target_id} active sur plan {plan_key}")


async def _check_referral_rewards(bot, referrer_id: int):
    """Verifie et attribue les recompenses de parrainage."""
    user = _get_user(referrer_id)
    count = user.get("referral_count", 0)
    rewarded = user.get("referral_rewarded", [])
    lang = get_lang(user)

    for threshold, tier in sorted(REFERRAL_TIERS.items()):
        if count >= threshold and threshold not in rewarded:
            reward = tier["reward"]
            if reward == "lifetime":
                _update_user(referrer_id, {"plan": "lifetime", "plan_expires": None})
            elif reward == "semestrial_3m":
                expires = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
                current = user.get("plan_expires")
                if current and current > datetime.now(timezone.utc).isoformat():
                    base = datetime.fromisoformat(current)
                else:
                    base = datetime.now(timezone.utc)
                expires = (base + timedelta(days=90)).isoformat()
                _update_user(referrer_id, {"plan": "semestrial", "plan_expires": expires})
            else:
                current = user.get("plan_expires")
                if current and current > datetime.now(timezone.utc).isoformat():
                    base = datetime.fromisoformat(current)
                else:
                    base = datetime.now(timezone.utc)
                duration = PLANS.get(reward, {}).get("duration_days", 30)
                expires = (base + timedelta(days=duration)).isoformat()
                _update_user(referrer_id, {"plan": reward, "plan_expires": expires})

            rewarded.append(threshold)
            _update_user(referrer_id, {"referral_rewarded": rewarded})

            invite_link = await _grant_channel_access(bot, referrer_id)
            msg = t("referral_reward", lang, count=threshold, reward=tier["label"])
            if invite_link:
                msg += f"\n\n{t('join_channel', lang)}\n{invite_link}"
            try:
                await bot.send_message(chat_id=referrer_id, text=msg, parse_mode="Markdown")
            except Exception:
                pass
            logger.info("Referral reward: user %d atteint %d filleuls -> %s", referrer_id, threshold, reward)


async def cmd_referral(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/referral — Affiche le lien de parrainage et les stats."""
    chat_id = update.effective_chat.id
    user = _get_user(chat_id)
    tg_lang = update.effective_user.language_code if update.effective_user else None
    lang = get_lang(user, tg_lang)

    ref_code = user.get("referral_code", str(chat_id))
    count = user.get("referral_count", 0)
    link = f"https://t.me/ScoreRadarFR_Bot?start=ref_{ref_code}"

    # Prochain palier
    next_tier = None
    for threshold in sorted(REFERRAL_TIERS.keys()):
        if count < threshold:
            next_tier = threshold
            break

    await update.message.reply_text(
        t("referral_info", lang, link=link, count=count, next_tier=next_tier or "✅",
          next_reward=REFERRAL_TIERS.get(next_tier, {}).get("label", t("referral_all_unlocked", lang))),
        parse_mode="Markdown",
    )


async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/lang — Choisir la langue."""
    chat_id = update.effective_chat.id
    user = _get_user(chat_id)
    tg_lang = update.effective_user.language_code if update.effective_user else None
    lang = get_lang(user, tg_lang)

    keyboard = []
    for code, label in LANG_FLAGS.items():
        keyboard.append([InlineKeyboardButton(label, callback_data=f"lang_{code}")])

    await update.message.reply_text(
        t("lang_title", lang),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def callback_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gere les clics sur les boutons de langue."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    lang_code = query.data.replace("lang_", "")

    if lang_code not in SUPPORTED_LANGS:
        return

    _update_user(chat_id, {"lang": lang_code})
    await query.edit_message_text(t("lang_set", lang_code), parse_mode="Markdown")


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/stop — Désactive les alertes."""
    chat_id = update.effective_chat.id
    user = _get_user(chat_id)
    tg_lang = update.effective_user.language_code if update.effective_user else None
    lang = get_lang(user, tg_lang)
    _update_user(chat_id, {"active": False})
    await update.message.reply_text(t("alerts_off", lang))


async def cmd_live(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/live — Affiche les matchs en cours."""
    chat_id = update.effective_chat.id
    user = _get_user(chat_id)
    tg_lang = update.effective_user.language_code if update.effective_user else None
    lang = get_lang(user, tg_lang)

    await update.message.reply_text(t("loading_matches", lang))

    fixtures = await get_live_fixtures(user["leagues"])

    if not fixtures:
        await update.message.reply_text(t("no_live_matches", lang))
        return

    lines = [f"{t('live_title', lang)}\n", f"{t('start_separator', lang)}\n"]

    current_league = ""
    for fixture in fixtures:
        info = parse_fixture_info(fixture)
        league = info["league_name"]
        if league != current_league:
            current_league = league
            lines.append(f"\n🏆 *{league}*")

        lines.append(
            f"  {info['home_team']} {info['home_goals']}-{info['away_goals']} "
            f"{info['away_team']} ({info['elapsed']}')"
        )

    lines.append(f"\n\n{t('matches_count', lang, count=len(fixtures))}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_leagues(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/leagues — Sélectionner les championnats à suivre."""
    chat_id = update.effective_chat.id
    user = _get_user(chat_id)
    tg_lang = update.effective_user.language_code if update.effective_user else None
    lang = get_lang(user, tg_lang)
    user_leagues = user.get("leagues", [])

    keyboard = []
    for league_id, league_name in POPULAR_LEAGUES.items():
        status = "✅" if league_id in user_leagues else "❌"
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {league_name}",
                callback_data=f"league_{league_id}",
            )
        ])

    keyboard.append([InlineKeyboardButton(t("select_all", lang), callback_data="league_all")])
    keyboard.append([InlineKeyboardButton(t("deselect_all", lang), callback_data="league_none")])

    await update.message.reply_text(
        t("leagues_title", lang),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def callback_league(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les clics sur les boutons de ligues."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    user = _get_user(chat_id)
    user_leagues = user.get("leagues", [])

    data = query.data

    if data == "league_all":
        user_leagues = list(POPULAR_LEAGUES.keys())
    elif data == "league_none":
        user_leagues = []
    elif data.startswith("league_"):
        league_id = int(data.replace("league_", ""))
        if league_id in user_leagues:
            user_leagues.remove(league_id)
        else:
            user_leagues.append(league_id)

    _update_user(chat_id, {"leagues": user_leagues})

    # Rafraîchir le clavier
    keyboard = []
    for league_id, league_name in POPULAR_LEAGUES.items():
        status = "✅" if league_id in user_leagues else "❌"
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {league_name}",
                callback_data=f"league_{league_id}",
            )
        ])
    user = _get_user(chat_id)
    tg_lang = query.from_user.language_code if query.from_user else None
    lang = get_lang(user, tg_lang)
    keyboard.append([InlineKeyboardButton(t("select_all", lang), callback_data="league_all")])
    keyboard.append([InlineKeyboardButton(t("deselect_all", lang), callback_data="league_none")])

    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))


async def cmd_sensitivity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/sensitivity [valeur] — Régler le seuil de confiance."""
    chat_id = update.effective_chat.id
    user = _get_user(chat_id)
    tg_lang = update.effective_user.language_code if update.effective_user else None
    lang = get_lang(user, tg_lang)

    args = context.args
    if not args:
        await update.message.reply_text(
            f"{t('sensitivity_title', lang)}\n\n"
            f"{t('sensitivity_current', lang, value=user['threshold'])}\n\n"
            f"{t('sensitivity_usage', lang)}",
            parse_mode="Markdown",
        )
        return

    try:
        value = int(args[0])
        if not 10 <= value <= 95:
            raise ValueError
    except ValueError:
        await update.message.reply_text(t("sensitivity_invalid", lang))
        return

    _update_user(chat_id, {"threshold": value})
    await update.message.reply_text(t("sensitivity_updated", lang, value=value), parse_mode="Markdown")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/status — Affiche la config actuelle."""
    chat_id = update.effective_chat.id
    user = _get_user(chat_id)
    tg_lang = update.effective_user.language_code if update.effective_user else None
    lang = get_lang(user, tg_lang)

    league_names = [
        POPULAR_LEAGUES.get(lid, f"ID:{lid}")
        for lid in user.get("leagues", [])
    ]

    status = t("status_active", lang) if user.get("active") else t("status_inactive", lang)

    await update.message.reply_text(
        f"{t('status_title', lang)}\n\n"
        f"{t('start_separator', lang)}\n"
        f"\n"
        f"{status}\n"
        f"{t('status_threshold', lang, value=user.get('threshold', DEFAULT_CONFIDENCE_THRESHOLD))}\n"
        f"{t('status_leagues', lang, count=len(league_names))}\n"
        + "\n".join(f"  • {name}" for name in league_names[:10])
        + (f"\n{t('status_more', lang, count=len(league_names) - 10)}" if len(league_names) > 10 else "")
        + f"\n\n{t('status_scan', lang, interval=CHECK_INTERVAL_SECONDS)}",
        parse_mode="Markdown",
    )






# --- /best --- Top 5 picks de la semaine ---

async def cmd_best(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/best — Top 5 picks gagnants de la semaine."""
    chat_id = update.effective_chat.id
    user = _get_user(chat_id)
    tg_lang = update.effective_user.language_code if update.effective_user else None
    lang = get_lang(user, tg_lang)

    try:
        from google_sheets import get_week_results
        results = get_week_results()
    except Exception as e:
        logger.error("Erreur /best: %s", e)
        await update.message.reply_text("Erreur lors de la recuperation des donnees.")
        return

    if not results:
        await update.message.reply_text("Aucun pick cette semaine.")
        return

    wins = [r for r in results if r.get("result") == "Win"]
    wins.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    top5 = wins[:5]

    if not top5:
        await update.message.reply_text("Aucun pick gagnant cette semaine (pour l\u2019instant).")
        return

    lines = ["\u2b50 TOP 5 PICKS DE LA SEMAINE\n"]
    for i, r in enumerate(top5, 1):
        lines.append(
            "%d. %s \u2014 %s" % (i, r["teams"], r.get("pick", "?"))
        )
        lines.append(
            "   Confiance: %s/100 \u2022 Score: %s\n" % (r.get("confidence", "?"), r.get("score", "?"))
        )

    total = len(results)
    total_wins = len(wins)
    wr = round(total_wins / total * 100) if total > 0 else 0
    lines.append("\n\U0001f4ca Semaine: %d/%d (%d%% winrate)" % (total_wins, total, wr))

    await update.message.reply_text("\n".join(lines))


# --- /next --- Prochains matchs avec potentiel ---

async def cmd_next(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/next \u2014 Matchs du jour a surveiller."""
    chat_id = update.effective_chat.id
    user = _get_user(chat_id)

    try:
        from footystats import get_todays_matches as _gtm, parse_prematch_data as _ppd
        matches = await _gtm()
    except Exception as e:
        logger.error("Erreur /next: %s", e)
        await update.message.reply_text("Erreur lors de la recuperation des donnees.")
        return

    if not matches:
        await update.message.reply_text("Aucun match prevu aujourd\u2019hui.")
        return

    interesting = []
    for m in matches:
        pm = _ppd(m)
        avg = pm.get("avg_potential", 0)
        btts = pm.get("btts_potential", 0)
        odds_o25 = pm.get("odds_ft_over25", 0)

        potential = 0
        if avg > 2.5:
            potential += 30
        elif avg > 2.0:
            potential += 15
        if btts > 60:
            potential += 25
        elif btts > 50:
            potential += 10
        if 0 < odds_o25 < 1.8:
            potential += 25
        elif 0 < odds_o25 < 2.0:
            potential += 10

        if potential >= 20:
            interesting.append({
                "home": m.get("home_name", "?"),
                "away": m.get("away_name", "?"),
                "league": m.get("competition_name", "?"),
                "avg": avg,
                "btts": btts,
                "odds_o25": odds_o25,
                "potential": potential,
            })

    interesting.sort(key=lambda x: x["potential"], reverse=True)
    top = interesting[:8]

    if not top:
        await update.message.reply_text("Aucun match a fort potentiel aujourd\u2019hui.")
        return

    lines = ["\U0001f50e MATCHS A SURVEILLER\n"]
    for m in top:
        parts = []
        if m["avg"] > 0:
            parts.append("Avg %.1f" % m["avg"])
        if m["btts"] > 0:
            parts.append("BTTS %.0f%%" % m["btts"])
        if m["odds_o25"] > 0:
            parts.append("@%.2f" % m["odds_o25"])
        details = " \u2022 ".join(parts)
        lines.append("\U0001f3c6 %s" % m["league"])
        lines.append("  %s vs %s" % (m["home"], m["away"]))
        lines.append("  %s\n" % details)

    lines.append("%d matchs a potentiel detectes." % len(interesting))
    await update.message.reply_text("\n".join(lines))

# --- Job verification paiements Stripe ---

async def check_stripe_payments(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Verifie les paiements Stripe completes et active les plans."""
    if not STRIPE_SECRET_KEY:
        return

    stripe.api_key = STRIPE_SECRET_KEY

    try:
        # Chercher les sessions payees dans les 10 dernieres minutes
        sessions = stripe.checkout.Session.list(
            status="complete",
            created={"gte": int((datetime.now(timezone.utc) - timedelta(minutes=10)).timestamp())},
            limit=20,
        )
    except Exception as e:
        logger.error("Erreur Stripe list sessions: %s", e)
        return

    for session in sessions.data:
        ref = session.client_reference_id
        if not ref or "_" not in ref:
            continue

        parts = ref.split("_", 1)
        chat_id = int(parts[0])
        plan_key = parts[1]

        if plan_key not in PLANS:
            continue

        # Verifier si deja active (eviter doublon)
        user = _get_user(chat_id)
        if user.get("stripe_last_session") == session.id:
            continue

        plan = PLANS[plan_key]
        if plan_key == "lifetime":
            _update_user(chat_id, {"plan": "lifetime", "plan_expires": None, "stripe_last_session": session.id})
        else:
            expires = (datetime.now(timezone.utc) + timedelta(days=plan["duration_days"])).isoformat()
            _update_user(chat_id, {"plan": plan_key, "plan_expires": expires, "stripe_last_session": session.id})

        invite_link = await _grant_channel_access(context.bot, chat_id)

        user = _get_user(chat_id)
        lang = get_lang(user)
        msg = t("payment_received", lang, plan=plan['name']) + "\n\n"
        if invite_link:
            msg += f"{t('join_channel', lang)}\n{invite_link}\n\n"
        if plan_key == "lifetime":
            msg += t("lifetime_thanks", lang)
        else:
            msg += t("expires_on", lang, date=_plan_expiry_str(user, lang))

        try:
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
        except Exception:
            pass

        logger.info("Stripe paiement OK: user %d -> plan %s (session %s)", chat_id, plan_key, session.id)

        # Crediter le parrain si le user a ete parraine
        user = _get_user(chat_id)
        referrer = user.get("referred_by")
        if referrer:
            referrer_user = _get_user(int(referrer))
            new_count = referrer_user.get("referral_count", 0) + 1
            _update_user(int(referrer), {"referral_count": new_count})
            await _check_referral_rewards(context.bot, int(referrer))
            logger.info("Referral credit: user %s -> parrain %s (total: %d)", chat_id, referrer, new_count)


# --- Job auto-kick des abonnements expires ---

async def check_expired_plans(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Verifie toutes les minutes les plans expires et kick du canal."""
    users = _load_users()
    now = datetime.now(timezone.utc).isoformat()

    for uid, user_data in users.items():
        plan = user_data.get("plan")
        if not plan or plan == "lifetime":
            continue
        expires = user_data.get("plan_expires")
        if not expires:
            continue
        if now >= expires:
            # Plan expire
            _update_user(int(uid), {"plan": None, "plan_expires": None})
            await _kick_from_channel(context.bot, int(uid))
            user_data_fresh = _get_user(int(uid))
            lang = get_lang(user_data_fresh)
            try:
                await context.bot.send_message(
                    chat_id=int(uid),
                    text=t("sub_expired", lang),
                )
            except Exception:
                pass
            logger.info("Plan expire: user %s kick du canal", uid)


def _get_goal_minute(fi, goals_at_alert):
    """Retourne la minute du but qui a declenche la validation (goals_at_alert + 1)."""
    events = fi.get("events", [])
    goal_events = [e for e in events if e.get("type") == "Goal"]
    goal_events_sorted = sorted(goal_events, key=lambda e: e.get("time", {}).get("elapsed", 0))
    idx = goals_at_alert  # 0-based index du but validant
    if idx < len(goal_events_sorted):
        t = goal_events_sorted[idx].get("time", {})
        m = t.get("elapsed", None)
        extra = t.get("extra")
        if m is not None:
            return "%s+%s" % (m, extra) if extra else str(m)
    return str(fi.get("elapsed", "?"))


# --- Scheduler : analyse automatique des matchs ---


async def check_matches(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job planifié — vérifie les matchs et envoie des alertes."""
    users = _load_users()

    if not users:
        return

    # Récupérer toutes les ligues suivies par au moins un utilisateur
    all_leagues = set()
    for user_data in users.values():
        if user_data.get("active"):
            all_leagues.update(user_data.get("leagues", []))

    if not all_leagues:
        all_leagues = set(str(lid) for lid in POPULAR_LEAGUES.keys())

    # --- Scan intelligent ---
    import time as _time_mod
    _now_utc = datetime.now(timezone.utc)
    _is_night = _now_utc.hour < 10 or _now_utc.hour >= 23
    _skip_analysis = False

    if _is_night:
        if not hasattr(check_matches, "_last_night_scan"):
            check_matches._last_night_scan = 0
        if (_time_mod.time() - check_matches._last_night_scan) < 600:
            logger.debug("Mode nuit: skip analyse")
            _skip_analysis = True
        else:
            check_matches._last_night_scan = _time_mod.time()

    fixtures = []
    if not _skip_analysis:
        logger.debug("Scan des matchs en direct (%d ligues)...", len(all_leagues))
        try:
            fixtures = await get_live_fixtures(list(all_leagues))
        except Exception as e:
            logger.error("Erreur récup matchs: %s", e)
            fixtures = []
        if fixtures:
            logger.debug("Analyse de %d matchs...", len(fixtures))
        else:
            logger.debug("Aucun match en direct.")

    # Charger les données pré-match FootyStats (avec cache 30 min)
    try:
        footystats_matches = await get_todays_matches()
    except Exception as e:
        logger.error("Erreur FootyStats: %s", e)
        footystats_matches = []

    # --- Vérifier les résultats (live + terminés) ---
    if not hasattr(check_matches, "_pending_results"):
        check_matches._pending_results = _load_pending_results()

    if check_matches._pending_results:
        # Récupérer TOUS les matchs live (pas filtrés) pour détecter les terminés
        try:
            all_fixtures = await get_live_fixtures()
        except Exception:
            all_fixtures = []

        # Construire un dict des matchs en cours par fixture_id (string keys)
        live_ids = set()
        live_fixtures = {}
        finished_fixtures = {}
        for f in all_fixtures:
            fi = parse_fixture_info(f)
            fid = str(fi["fixture_id"])
            live_ids.add(fid)
            if fi["status_short"] in ("FT", "AET", "PEN"):
                finished_fixtures[fid] = fi
            else:
                live_fixtures[fid] = fi

        # Mettre à jour les couleurs live (par pick, sans notification)
        for pkey, pending in check_matches._pending_results.items():
            fid = pending.get("fixture_id", pkey)
            if fid in live_fixtures:
                fi = live_fixtures[fid]
                current_goals = fi["home_goals"] + fi["away_goals"]
                try:
                    update_live_colors(pending["row_nums"], current_goals)
                except Exception as e:
                    logger.error("Erreur update live colors: %s", e)

        # Grouper les picks par fixture pour notifications regroupées
        by_fixture = {}
        for pkey, pending in check_matches._pending_results.items():
            fid = pending.get("fixture_id", pkey)
            if fid not in by_fixture:
                by_fixture[fid] = []
            by_fixture[fid].append((pkey, pending))

        to_remove = []

        for fid, fixture_picks in by_fixture.items():

            # --- Match terminé → notification groupée finale ---
            if fid in finished_fixtures:
                fi = finished_fixtures[fid]
                final_goals = fi["home_goals"] + fi["away_goals"]
                final_score = "%d - %d" % (fi["home_goals"], fi["away_goals"])
                home = fixture_picks[0][1]["home"]
                away = fixture_picks[0][1]["away"]

                # FT: un seul message pour la DERNIERE alerte du match (goals_at_alert le plus élevé)
                sorted_picks = sorted(fixture_picks, key=lambda x: x[1]["goals_at_alert"])
                last_pk2, last_p2 = sorted_picks[-1]
                _ds = last_p2.get("dominant_side", "home")
                _dga = last_p2.get("dom_goals_at_alert", 0)
                _df = fi["home_goals"] if _ds == "home" else fi["away_goals"]
                won_prio = final_goals > last_p2["goals_at_alert"]
                won_team = _df > _dga
                s_prio = "✅" if won_prio else "❌"
                s_team = "✅" if won_team else "❌"
                _ar = last_p2.get("pick_agg_result")
                if _ar is None:
                    _ar = "win" if _df > _dga else "lose"
                s_agg = "✅" if _ar == "win" else "❌"
                pick_lines = ["🏁 FT | %s %d-%d %s\n" % (home, fi["home_goals"], fi["away_goals"], away)]
                pick_lines.append("• %s %s" % (s_prio, last_p2.get("pick_prio", "Over %.1f FT" % (last_p2["goals_at_alert"] + 0.5))))
                if last_p2.get("pick_team"):
                    pick_lines.append("• %s %s" % (s_team, last_p2["pick_team"]))
                if last_p2.get("pick_agg"):
                    pick_lines.append("• %s %s" % (s_agg, last_p2["pick_agg"]))
                result_msg = "\n".join(pick_lines)
                reply_to = last_p2.get("channel_message_id")
                if CHANNEL_USERNAME:
                    try:
                        await context.bot.send_message(
                            chat_id=CHANNEL_USERNAME,
                            text=result_msg,
                            reply_to_message_id=reply_to,
                        )
                    except Exception:
                        pass
                for pk2, p2 in fixture_picks:
                    p2["notified_result"] = True
                logger.info("FT notif unique: %s vs %s -> %s", home, away, final_score)
                _save_pending_results(check_matches._pending_results)

                for pk2, p2 in fixture_picks:
                    try:
                        _ds2 = p2.get("dominant_side", "")
                        _dga2 = p2.get("dom_goals_at_alert", 0)
                        _tpw2 = (fi["home_goals"] if _ds2 == "home" else fi["away_goals"]) > _dga2 if _ds2 else None
                        update_result(p2["row_nums"], final_score, final_goals, fixture_id=fid, team_pick_win=_tpw2)
                    except Exception as e:
                        logger.error("Erreur update resultat: %s", e)
                    to_remove.append(pk2)

            # --- Match en cours → notification groupée si nouveau but ---
            elif fid in live_fixtures:
                fi = live_fixtures[fid]
                current_goals = fi["home_goals"] + fi["away_goals"]
                elapsed = fi.get("elapsed", "?")
                home = fixture_picks[0][1]["home"]
                away = fixture_picks[0][1]["away"]

                newly_won = [(pk, p) for pk, p in fixture_picks
                             if current_goals > p["goals_at_alert"] and not p.get("notified_win")]
                # Un reply par alerte (pick) — chaque alerte a son propre message de validation
                for pk2, p2 in sorted(newly_won, key=lambda x: x[1]["goals_at_alert"]):
                    _ds = p2.get("dominant_side", "home")
                    _dga = p2.get("dom_goals_at_alert", 0)
                    _dn = fi["home_goals"] if _ds == "home" else fi["away_goals"]
                    if current_goals > p2["goals_at_alert"] and p2.get("pick_agg_result") is None:
                        p2["pick_agg_result"] = "win" if _dn > _dga else "lose"
                    s_prio = "✅" if current_goals > p2["goals_at_alert"] else "⏳"
                    if s_prio == "✅":
                        p2["notified_win"] = True
                    s_team = "✅" if _dn > _dga else "⏳"
                    _ar = p2.get("pick_agg_result")
                    s_agg = "✅" if _ar == "win" else ("❌" if _ar == "lose" else "⏳")
                    if s_team == "⏳" or s_agg == "⏳":
                        p2["needs_ft"] = True
                    goal_min = _get_goal_minute(fi, p2["goals_at_alert"])
                    _nl = chr(10)
                    pick_lines = ["🔄 %s' | %s %d-%d %s" % (goal_min, home, fi["home_goals"], fi["away_goals"], away) + _nl]
                    pick_lines.append("• %s %s" % (s_prio, p2.get("pick_prio", "Over %.1f FT" % (p2["goals_at_alert"] + 0.5))))
                    if p2.get("pick_team"):
                        pick_lines.append("• %s %s" % (s_team, p2["pick_team"]))
                    if p2.get("pick_agg"):
                        pick_lines.append("• %s %s" % (s_agg, p2["pick_agg"]))
                    win_msg = "\n".join(pick_lines)
                    reply_to = p2.get("channel_message_id")
                    if CHANNEL_USERNAME:
                        try:
                            await context.bot.send_message(
                                chat_id=CHANNEL_USERNAME,
                                text=win_msg,
                                reply_to_message_id=reply_to,
                            )
                        except Exception:
                            pass
                    for uid, user_data in users.items():
                        if user_data.get("active") and int(uid) != ADMIN_ID:
                            try:
                                await context.bot.send_message(chat_id=int(uid), text=win_msg)
                            except Exception:
                                pass
                if newly_won:
                    logger.info("Win notif par alerte: %s vs %s -> %s' %d-%d",
                                home, away, elapsed, fi["home_goals"], fi["away_goals"])
                    _save_pending_results(check_matches._pending_results)

            # --- Match disparu du live -> recuperer le score final et notifier ---
            else:
                try:
                    raw = await get_fixture_by_id(int(fid))
                except Exception:
                    raw = {}
                if raw:
                    fi = parse_fixture_info(raw)
                    final_goals = fi["home_goals"] + fi["away_goals"]
                    final_score = "%d - %d" % (fi["home_goals"], fi["away_goals"])
                    home = fixture_picks[0][1]["home"]
                    away = fixture_picks[0][1]["away"]
                    # Un seul message FT pour la dernière alerte
                    sorted_picks2 = sorted(fixture_picks, key=lambda x: x[1]["goals_at_alert"])
                    last_pk2b, last_p2b = sorted_picks2[-1]
                    _ds = last_p2b.get("dominant_side", "home")
                    _dga = last_p2b.get("dom_goals_at_alert", 0)
                    _df = fi["home_goals"] if _ds == "home" else fi["away_goals"]
                    won_prio = final_goals > last_p2b["goals_at_alert"]
                    won_team = _df > _dga
                    s_prio = "✅" if won_prio else "❌"
                    s_team = "✅" if won_team else "❌"
                    _ar = last_p2b.get("pick_agg_result")
                    if _ar is None:
                        _ar = "win" if _df > _dga else "lose"
                    s_agg = "✅" if _ar == "win" else "❌"
                    _nl2 = chr(10)
                    pick_lines = ["🏁 FT | %s %d-%d %s" % (home, fi["home_goals"], fi["away_goals"], away) + _nl2]
                    pick_lines.append("• %s %s" % (s_prio, last_p2b.get("pick_prio", "Over %.1f FT" % (last_p2b["goals_at_alert"] + 0.5))))
                    if last_p2b.get("pick_team"):
                        pick_lines.append("• %s %s" % (s_team, last_p2b["pick_team"]))
                    if last_p2b.get("pick_agg"):
                        pick_lines.append("• %s %s" % (s_agg, last_p2b["pick_agg"]))
                    result_msg = chr(10).join(pick_lines)
                    reply_to = last_p2b.get("channel_message_id")
                    if CHANNEL_USERNAME:
                        try:
                            await context.bot.send_message(
                                chat_id=CHANNEL_USERNAME,
                                text=result_msg,
                                reply_to_message_id=reply_to,
                            )
                        except Exception:
                            pass
                    for pk2, p2 in fixture_picks:
                        p2["notified_result"] = True
                    logger.info("FT notif unique (disparu): %s vs %s -> %s", home, away, final_score)
                    try:
                        for pk2d, p2d in fixture_picks:
                            _ds2d = p2d.get("dominant_side", "")
                            _dga2d = p2d.get("dom_goals_at_alert", 0)
                            _tpw2d = (fi["home_goals"] if _ds2d == "home" else fi["away_goals"]) > _dga2d if _ds2d else None
                            update_result(p2d["row_nums"], final_score, final_goals, fixture_id=fid, team_pick_win=_tpw2d)
                    except Exception as e:
                        logger.error("Erreur update resultat (disparu): %s", e)
                    _save_pending_results(check_matches._pending_results)
                for pk2, _ in fixture_picks:
                    to_remove.append(pk2)

        if to_remove:
            for pkey in set(to_remove):
                if pkey in check_matches._pending_results:
                    del check_matches._pending_results[pkey]
            _save_pending_results(check_matches._pending_results)


    for fixture in fixtures:
        info = parse_fixture_info(fixture)
        fixture_id = info["fixture_id"]

        # Ignorer les matchs pas encore commencés ou terminés
        if info["status_short"] not in ("1H", "2H", "HT", "ET", "P"):
            continue

        # Skip matchs < 17 min (sauf si alerte active avec nouveaux buts)
        _elapsed_check = info.get("elapsed", 0)
        if _elapsed_check and _elapsed_check < 17:
            _fid_str = str(fixture_id)
            _has_pending = (hasattr(check_matches, "_pending_results")
                           and _fid_str in check_matches._pending_results)
            if _has_pending:
                _pe = check_matches._pending_results[_fid_str]
                _cur = info["home_goals"] + info["away_goals"]
                if _cur <= _pe.get("goals_at_alert", 0):
                    continue
            else:
                continue

        try:
            stats_raw = await get_fixture_statistics(fixture_id)
            await asyncio.sleep(0.25)  # Éviter le rate limit API-Football
        except Exception as e:
            logger.error("Erreur stats fixture %s: %s", fixture_id, e)
            continue

        if not stats_raw:
            continue

        # Chercher les données pré-match FootyStats
        prematch = None
        if footystats_matches:
            fs_match = find_match_data(info["home_team"], info["away_team"], footystats_matches)
            if fs_match:
                prematch = parse_prematch_data(fs_match)
                logger.info("FootyStats match: %s vs %s -> odds_over25=%.2f",
                            info["home_team"], info["away_team"],
                            prematch.get("odds_ft_over25", 0))
            else:
                logger.warning("FootyStats: pas de match trouvé pour %s vs %s",
                               info["home_team"], info["away_team"])
        else:
            logger.warning("FootyStats: aucun match du jour chargé")

        stats = parse_statistics(stats_raw)
        signal = analyze_match(info, stats, prematch=prematch)

        if signal is None:
            continue

        confidence = signal["confidence"]
        elapsed = info.get("elapsed", 0)
        message = format_signal(signal, lang="en")  # Canal en anglais

        # Temps additionnel : en 1ère mi-temps (1H), elapsed peut dépasser 45
        # (ex: 45+3 = 48). On normalise pour que les seuils s'appliquent
        # correctement. En 2H, elapsed > 90 = temps additionnel fin de match.
        status_short = info["status_short"]
        effective_elapsed = elapsed
        if status_short == "1H" and elapsed > 45:
            effective_elapsed = 45  # Temps additionnel 1ère mi-temps → traiter comme 45'
        elif status_short == "HT":
            effective_elapsed = 45  # Mi-temps → traiter comme 45'

        # Bloquer les alertes après 85' sauf prolongations (ET/P)
        # Les matchs de coupe/Europe peuvent avoir des prolongations
        if effective_elapsed >= 85 and status_short not in ("ET", "P"):
            continue

        # Seuil dynamique selon la minute du match
        # Plus le match avance, plus on exige de confiance
        if effective_elapsed >= 80:
            min_confidence = 93
        elif effective_elapsed >= 70:
            min_confidence = 85
        else:
            min_confidence = 75

        if confidence < min_confidence:
            continue

        # Anti-spam : 1 seule alerte par pick (même match + même Over = bloqué)
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
                continue

        # Récupérer la cote live Over au moment du bet
        over_line = total_goals + 0.5  # ex: 0 buts → Over 0.5, 2 buts → Over 2.5
        try:
            live_odd = await get_live_odds(fixture_id, over_line)
            if live_odd:
                signal["live_odds"] = live_odd
                logger.info("Cote live Over %.1f: %.2f (%s vs %s)",
                            over_line, live_odd, info["home_team"], info["away_team"])
        except Exception as e:
            logger.error("Erreur récup cote live: %s", e)

        # Envoyer dans le canal
        if CHANNEL_USERNAME:
            try:
                sent_alert = await context.bot.send_message(chat_id=CHANNEL_USERNAME, text=message)
                check_matches._alerted_picks.add(pick_key)
                _save_alerted_picks(check_matches._alerted_picks)
                logger.info("Alerte canal pour %s vs %s (conf: %d, pick: Over %.1f)",
                            info["home_team"], info["away_team"], confidence, total_goals + 0.5)
                # Logger dans Google Sheets
                try:
                    row_num = log_alert(signal, fixture_id=fixture_id)
                    if row_num:
                        if not hasattr(check_matches, "_pending_results"):
                            check_matches._pending_results = _load_pending_results()
                        if pick_key not in check_matches._pending_results:
                            _dom_side = signal.get("dominant_side", "home")
                            _dom_team = signal.get("dominant_team", info["home_team"])
                            _dom_goals_at = info["home_goals"] if _dom_side == "home" else info["away_goals"]
                            check_matches._pending_results[pick_key] = {
                                "fixture_id": str(fixture_id),
                                "row_nums": [],
                                "home": info["home_team"],
                                "away": info["away_team"],
                                "goals_at_alert": total_goals,
                                "home_goals_at_alert": info["home_goals"],
                                "away_goals_at_alert": info["away_goals"],
                                "dominant_side": _dom_side,
                                "dominant_team": _dom_team,
                                "dom_goals_at_alert": _dom_goals_at,
                                "pick_prio": "Over %.1f FT" % (total_goals + 0.5),
                                "pick_team": "Over %.1f %s" % (_dom_goals_at + 0.5, _dom_team),
                                "pick_agg": "Prochain but — %s" % _dom_team,
                                "pick_agg_result": None,
                                "notified_win": False,
                                "channel_message_id": sent_alert.message_id if sent_alert else None,
                            }
                        if row_num not in check_matches._pending_results[pick_key]["row_nums"]:
                            check_matches._pending_results[pick_key]["row_nums"].append(row_num)
                        _save_pending_results(check_matches._pending_results)
                except Exception as sheet_err:
                    logger.error("Erreur Google Sheets: %s", sheet_err)
            except Exception as e:
                logger.error("Erreur envoi canal: %s", e)

        # Envoyer aux utilisateurs en DM
        for uid, user_data in users.items():
            if not user_data.get("active"):
                continue
            if int(uid) == ADMIN_ID:
                continue  # Admin voit deja le canal, pas de double DM
            if confidence < user_data.get("threshold", DEFAULT_CONFIDENCE_THRESHOLD):
                continue
            if info["league_id"] not in user_data.get("leagues", []):
                continue

            alerted = user_data.get("alerted_fixtures", [])
            if pick_key in alerted:
                continue

            try:
                user_lang = get_lang(user_data)
                user_message = format_signal(signal, lang=user_lang)
                await context.bot.send_message(chat_id=int(uid), text=user_message)
                alerted.append(pick_key)
                _update_user(int(uid), {"alerted_fixtures": alerted[-50:]})
                logger.info("Alerte DM à %s pour %s vs %s (conf: %d, lang: %s)",
                            uid, info["home_team"], info["away_team"], confidence, user_lang)
            except Exception as e:
                logger.error("Erreur envoi à %s: %s", uid, e)

    # --- Scanner le sheet pour les "En cours" orphelins (toutes les 5 min) ---
    if not hasattr(check_matches, "_last_sheet_scan"):
        check_matches._last_sheet_scan = 0

    import time as _time
    now_ts = _time.time()
    if now_ts - check_matches._last_sheet_scan > 300:  # 5 minutes
        check_matches._last_sheet_scan = now_ts
        try:
            pending_rows = get_pending_rows()
            logger.info("Sheet scan: %d lignes 'En cours' trouvées", len(pending_rows))
            if pending_rows:
                # Récupérer tous les matchs live (sans filtre) pour le score actuel
                try:
                    all_fx = await get_live_fixtures()
                except Exception:
                    all_fx = []

                # Construire dict: "equipe1 - equipe2" -> fixture_info
                live_by_teams = {}
                finished_by_teams = {}
                for f in all_fx:
                    fi = parse_fixture_info(f)
                    team_key = "%s - %s" % (fi["home_team"], fi["away_team"])
                    if fi["status_short"] in ("FT", "AET", "PEN"):
                        finished_by_teams[team_key] = fi
                    else:
                        live_by_teams[team_key] = fi

                for pr in pending_rows:
                    teams = pr["teams"]
                    row_num = pr["row_num"]

                    if teams in finished_by_teams:
                        fi = finished_by_teams[teams]
                        total = fi["home_goals"] + fi["away_goals"]
                        finalize_row(row_num, total)
                        logger.info("Sheet scan: %s terminé -> finalisé ligne %d", teams, row_num)
                    elif teams in live_by_teams:
                        fi = live_by_teams[teams]
                        total = fi["home_goals"] + fi["away_goals"]
                        update_live_colors([row_num], total)
                        logger.info("Sheet scan: %s en cours -> vérif live ligne %d", teams, row_num)
                    elif all_fx:
                        # Match disparu de l'API = terminé sans suivi
                        # Score n'a pas bougé depuis l'alerte -> finaliser avec score de l'alerte
                        score = pr.get("score_at_alert", "0 - 0")
                        if " - " in score:
                            parts = score.split(" - ")
                            goals = int(parts[0].strip()) + int(parts[1].strip())
                        else:
                            goals = 0
                        finalize_row(row_num, goals)
                        logger.info("Sheet scan: %s disparu de l'API -> finalisé ligne %d (score alerte: %s)",
                                     teams, row_num, score)

        except Exception as e:
            logger.error("Erreur scan sheet: %s", e)




# --- Twitter scheduled jobs ---

def _mark_daily_tweet_sent():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _TWEET_DATE_FILE.write_text(today)

def _daily_tweet_already_sent():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        return _TWEET_DATE_FILE.read_text().strip() == today
    except FileNotFoundError:
        return False

async def send_daily_tweet(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Poste le recap quotidien sur Twitter (22h UTC = 23h Paris)."""
    try:
        from google_sheets import get_all_rows
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
        result_val = row[9].strip() if len(row) > 9 else ""
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
        success = False
        if len(tweets) == 1:
            tweet_id = post_tweet(tweets[0])
            if tweet_id:
                _mark_daily_tweet_sent()
                success = True
            logger.info("Tweet recap quotidien poste (1 tweet)")
        else:
            ids = post_thread(tweets)
            if ids:
                _mark_daily_tweet_sent()
                success = True
            logger.info("Thread recap quotidien poste: %d tweets", len(ids))
        if not success:
            logger.warning("Tweet recap echoue, retry dans 5 minutes")
            context.job_queue.run_once(send_daily_tweet, when=300)


async def send_weekend_teaser(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Poste le teaser du week-end sur Twitter (11h UTC = 12h Paris)."""
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
    """Poste le thread recap hebdomadaire sur Twitter (dimanche 23h30 Paris)."""
    try:
        from google_sheets import get_week_results
        results = get_week_results()
    except Exception as e:
        logger.error("Tweet weekly: erreur sheet: %s", e)
        return

    if not results:
        logger.info("Tweet weekly: aucun resultat cette semaine, skip")
        return

    for r in results:
        if "league" not in r or not r["league"]:
            r["league"] = "Autre"

    tweets = build_weekly_thread(results)
    if tweets:
        ids = post_thread(tweets)
        logger.info("Thread weekly poste: %d tweets", len(ids))
        if not ids:
            logger.warning("Thread weekly echoue, retry dans 5 minutes")
            context.job_queue.run_once(send_weekly_tweet, when=300)




# --- Main ---

async def cmd_startadmin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/startadmin - Menu complet des plans (admin uniquement)."""
    chat_id = update.effective_chat.id
    if chat_id != ADMIN_ID:
        return
    user = _get_user(chat_id)
    tg_lang = update.effective_user.language_code if update.effective_user else None
    lang = get_lang(user, tg_lang)
    keyboard = [
        [InlineKeyboardButton(t("btn_trial", lang), callback_data="plan_trial")],
        [InlineKeyboardButton(t("btn_monthly", lang), callback_data="plan_monthly")],
        [InlineKeyboardButton(t("btn_semestrial", lang), callback_data="plan_semestrial")],
        [InlineKeyboardButton(t("btn_lifetime", lang), callback_data="plan_lifetime")],
    ]
    parts = [
        t("start_title", lang), "",
        t("start_separator", lang), "",
        t("start_desc", lang), "",
        t("choose_plan", lang), "",
        t("plan_trial", lang),
        t("plan_monthly", lang),
        t("plan_semestrial", lang),
        t("plan_lifetime", lang), "",
        chr(129309) + " /referral — " + t("referral_short", lang),
        chr(127757) + " /lang — " + t("lang_short", lang),
    ]
    await update.message.reply_text(
        chr(10).join(parts),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )

def main() -> None:
    """Lance le bot."""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "ton_token_ici":
        print("❌ ERREUR: Configure ton token Telegram dans le fichier .env")
        print("   TELEGRAM_BOT_TOKEN=ton_token_ici")
        return

    from config import API_FOOTBALL_KEY
    if not API_FOOTBALL_KEY or API_FOOTBALL_KEY == "ta_cle_api_ici":
        print("❌ ERREUR: Configure ta clé API-Football dans le fichier .env")
        print("   API_FOOTBALL_KEY=ta_cle_api_ici")
        return

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()


    # Commandes
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("startadmin", cmd_startadmin))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("live", cmd_live))
    app.add_handler(CommandHandler("leagues", cmd_leagues))
    app.add_handler(CommandHandler("sensitivity", cmd_sensitivity))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("activate", cmd_activate))
    app.add_handler(CommandHandler("lang", cmd_lang))
    app.add_handler(CommandHandler("referral", cmd_referral))
    app.add_handler(CommandHandler("best", cmd_best))
    app.add_handler(CommandHandler("next", cmd_next))

    # Callbacks (boutons inline)
    app.add_handler(CallbackQueryHandler(callback_plan, pattern=r"^plan_"))
    app.add_handler(CallbackQueryHandler(callback_stripe, pattern=r"^stripe_"))
    app.add_handler(CallbackQueryHandler(callback_stars, pattern=r"^stars_"))
    app.add_handler(CallbackQueryHandler(callback_league, pattern=r"^league_"))
    app.add_handler(CallbackQueryHandler(callback_lang, pattern=r"^lang_"))

    # Paiement Telegram Stars
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    # Jobs planifies
    job_queue = app.job_queue
    job_queue.run_repeating(check_matches, interval=CHECK_INTERVAL_SECONDS, first=10)
    job_queue.run_repeating(check_expired_plans, interval=60, first=30)
    job_queue.run_repeating(check_stripe_payments, interval=30, first=15)

    # Twitter schedulers
    from datetime import time as dt_time
    # Daily recap: 22h UTC (23h Paris) tous les jours
    job_queue.run_daily(send_daily_tweet, time=dt_time(hour=22, minute=0))
    # Weekend teaser: 11h UTC (12h Paris) samedi + dimanche
    job_queue.run_daily(send_weekend_teaser, time=dt_time(hour=11, minute=0), days=(5, 6))
    # Weekly thread Twitter: dimanche 23h30 heure Paris (ZoneInfo gere DST)
    from zoneinfo import ZoneInfo
    _paris = ZoneInfo("Europe/Paris")
    job_queue.run_daily(send_weekly_tweet, time=dt_time(hour=23, minute=30, tzinfo=_paris), days=(6,))

    # Catch-up: si le bot demarre apres 22h UTC et que le recap n'a pas ete envoye
    now_utc = datetime.now(timezone.utc)
    if now_utc.hour >= 22 and not _daily_tweet_already_sent():
        job_queue.run_once(send_daily_tweet, when=30)
        logger.info("Catch-up: tweet recap quotidien planifie dans 30s (bot demarre apres 22h UTC)")

    print("[OK] Goal Signal Bot demarre !")
    print(f"   Scan toutes les {CHECK_INTERVAL_SECONDS}s")
    print(f"   Seuil par defaut: {DEFAULT_CONFIDENCE_THRESHOLD}/100")
    print("   Ctrl+C pour arreter")

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
