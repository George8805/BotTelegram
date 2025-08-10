# app_test_redirect.py
import logging
import threading
from datetime import datetime

import requests
import stripe
from flask import Flask, request, redirect

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatMemberUpdated,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ChatMemberHandler,
)

# ---------------- CONFIG (test mode) ----------------
TELEGRAM_TOKEN = "8285233635:AAEmE6IsunZ8AXVxJ2iVh5fa-mY0ppoKcgQ"

STRIPE_SECRET_KEY = "sk_test_51RmH5NCFUXMdgQRziwrLse45qn00G24mL7ZYt1aEwiB9wFCTJUNcw9g8YLnVZY3k0VyQAKJdmGI0bnWa4og8qfYG00uTJvHUMQ"
STRIPE_WEBHOOK_SECRET = "whsec_test_LxOkuricKYEikXru9KjQje65g4MNapK9"

GROUP_CHAT_ID = -1002577679941
INVITE_LINK = "https://t.me/+rK1HDp49LEIyYmRk"
PUBLIC_BASE_URL = "https://example.com"  # înlocuiești cu domeniul tău real

stripe.api_key = STRIPE_SECRET_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("escorte-bot-test")

app = Flask(__name__)

active_subscriptions: dict[int, str] = {}


# ---------------- Helpers ----------------
def tg_send(chat_id: int, text: str, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
        "parse_mode": "HTML",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup.to_dict()
    requests.post(url, json=payload, timeout=10)


def add_user_flow(user_id: int):
    text = (
        "Bună,\n\n"
        "⭐ Aici veți găsi conținut premium și leaks.\n\n"
        "⭐ Pentru a intra în grup, trebuie să vă abonați.\n\n"
        "⭐ Vă mulțumim că ați ales să fiți membru!"
    )
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔗 Intră în grup", url=f"{PUBLIC_BASE_URL}/join")]]
    )
    tg_send(user_id, text, kb)


def remove_user_from_group(user_id: int):
    kick_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/kickChatMember"
    requests.post(
        kick_url,
        json={
            "chat_id": GROUP_CHAT_ID,
            "user_id": user_id,
            "until_date": int(datetime.now().timestamp()) + 60,
        },
        timeout=10,
    )
    unban_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/unbanChatMember"
    requests.post(
        unban_url,
        json={"chat_id": GROUP_CHAT_ID, "user_id": user_id},
        timeout=10,
    )


# ---------------- /join cu redirect 302 ----------------
@app.route("/join")
def join_group():
    try:
        invite_hash = INVITE_LINK.split('+', 1)[1]
    except Exception:
        invite_hash = ""
    return redirect(f"tg://join?invite={invite_hash}", code=302)


# ---------------- Stripe webhook ----------------
@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        logger.warning(f"Webhook verify failed: {e}")
        return "bad signature", 400

    etype = event["type"]
    obj = event["data"]["object"]
    logger.info(f"Stripe event: {etype}")

    if etype == "checkout.session.completed":
        chat_id = obj.get("metadata", {}).get("telegram_chat_id")
        subscription_id = obj.get("subscription")
        if chat_id and subscription_id:
            active_subscriptions[int(chat_id)] = subscription_id
            add_user_flow(int(chat_id))

    elif etype == "invoice.payment_succeeded":
        chat_id = obj.get("metadata", {}).get("telegram_chat_id")
        sub_id = obj.get("subscription")
        if chat_id and sub_id:
            active_subscriptions[int(chat_id)] = sub_id
            add_user_flow(int(chat_id))

    elif etype in ("invoice.payment_failed", "customer.subscription.deleted"):
        chat_id = obj.get("metadata", {}).get("telegram_chat_id")
        if chat_id:
            remove_user_from_group(int(chat_id))
            active_subscriptions.pop(int(chat_id), None)

    return "ok", 200


@app.route("/health")
def health():
    return "ok", 200


# ---------------- Telegram handlers ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        line_items=[{"price": "price_test_1RsNMwCFUXMdgQRzVlmVTBut", "quantity": 1}],
        success_url=f"{PUBLIC_BASE_URL}/join",
        cancel_url=f"{PUBLIC_BASE_URL}/join",
        metadata={"telegram_chat_id": str(chat_id)},
    )
    msg = (
        "Bună,\n\n"
        "⭐ Aici veți găsi conținut premium și leaks.\n"
        "⭐ Abonamentul costă 25 RON / 30 zile.\n"
        "⭐ Apasă butonul pentru a plăti:"
    )
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("💳 Plătește abonamentul de test", url=session.url)]]
    )
    await update.message.reply_text(msg, reply_markup=kb)


async def on_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u: ChatMemberUpdated = update.chat_member
    if u.chat.id != GROUP_CHAT_ID:
        return
    old = u.old_chat_member.status
    new = u.new_chat_member.status
    if old in ("member", "administrator") and new in ("left", "kicked"):
        user_id = u.from_user.id
        logger.info(f"User {user_id} a părăsit grupul -> remove")
        remove_user_from_group(user_id)


def run_flask():
    app.run(host="0.0.0.0", port=5000)


if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(ChatMemberHandler(on_chat_member, ChatMemberHandler.CHAT_MEMBER))
    application.add_handler(ChatMemberHandler(on_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    application.run_polling(drop_pending_updates=True)
