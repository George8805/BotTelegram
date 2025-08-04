import stripe
import logging
from datetime import datetime, timedelta
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import threading
import requests
import json
import os
import time

# ---------------- CONFIG ----------------
TELEGRAM_TOKEN = "8285233635:AAEmE6IsunZ8AXVxJ2iVh5fa-mY0ppoKcgQ"
STRIPE_SECRET_KEY = "sk_test_51RmH5NCFUXMdgQRziwrLse45qn00G24mL7ZYt1aEwiB9wFCTJUNcw9g8YLnVZY3k0VyQAKJdmGI0bnWa4og8qfYG00uTJvHUMQ"
STRIPE_WEBHOOK_SECRET = "whsec_S7AvDmiroK8REpBwWljjHY6p6ZCIsLGV"
PRODUCT_NAME = "Abonament Premium Test"
PRICE_RON = 25
SUCCESS_URL = "https://t.me/EscorteRO_bot"
CANCEL_URL = "https://t.me/EscorteRO_bot"

GROUP_CHAT_ID = -1002577679941
INVITE_LINK = "https://t.me/+rK1HDp49LEIyYmRk"
SUBSCRIPTIONS_FILE = "subscriptions.json"

stripe.api_key = STRIPE_SECRET_KEY

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- HELPER FUNCTIONS ----------------
def load_subscriptions():
    if os.path.exists(SUBSCRIPTIONS_FILE):
        with open(SUBSCRIPTIONS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_subscriptions(data):
    with open(SUBSCRIPTIONS_FILE, "w") as f:
        json.dump(data, f)

def send_telegram_message(chat_id, text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    )

def remove_user_from_group(user_id):
    """Kick + Unban pentru a permite reîntoarcerea imediată"""
    logger.info(f"🛑 Scoatem user {user_id} din grup...")
    # Kick
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/kickChatMember",
        json={"chat_id": GROUP_CHAT_ID, "user_id": user_id}
    )
    time.sleep(1)
    # Unban
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/unbanChatMember",
        json={"chat_id": GROUP_CHAT_ID, "user_id": user_id}
    )
    logger.info(f"✅ User {user_id} scos și debanat imediat.")

# ---------------- THREAD DE VERIFICARE ----------------
def check_expired_subscriptions():
    while True:
        subs = load_subscriptions()
        changed = False
        now = datetime.now()

        for chat_id, expiry_str in list(subs.items()):
            expiry = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")
            if now > expiry:
                try:
                    remove_user_from_group(int(chat_id))
                    send_telegram_message(chat_id, "❌ Abonamentul tău a expirat. Plătește din nou pentru a reintra.")
                except Exception as e:
                    logger.error(f"Eroare la eliminare utilizator {chat_id}: {e}")
                del subs[chat_id]
                changed = True

        if changed:
            save_subscriptions(subs)

        time.sleep(10)  # verifică la fiecare 10 secunde

# ---------------- FLASK APP ----------------
app = Flask(__name__)

@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        logger.error(f"⚠️ Webhook error: {str(e)}")
        return f"⚠️ Webhook error: {str(e)}", 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        chat_id = session.get("metadata", {}).get("telegram_chat_id")

        if chat_id:
            logger.info(f"💰 Plata confirmată pentru {chat_id}")

            # abonament test = 1 minut
            expiry_date = datetime.now() + timedelta(minutes=1)
            subs = load_subscriptions()
            subs[str(chat_id)] = expiry_date.strftime("%Y-%m-%d %H:%M:%S")
            save_subscriptions(subs)

            send_telegram_message(chat_id, f"✅ Plata confirmată! Abonamentul tău este activ până la {expiry_date.strftime('%H:%M:%S')}.\n\nIntră în grup aici: {INVITE_LINK}")

    return "✅ Webhook received", 200

# ---------------- TELEGRAM BOT ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    logger.info(f"📩 Comanda /start de la {chat_id}")

    text = (
        "Bună,\n\n"
        f"⭐ Abonament test: {PRICE_RON} RON / 1 minut.\n"
        "⭐ Apasă butonul pentru a plăti."
    )

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "ron",
                "product_data": {"name": PRODUCT_NAME},
                "unit_amount": int(PRICE_RON * 100),
            },
            "quantity": 1
        }],
        mode="payment",
        success_url=SUCCESS_URL,
        cancel_url=CANCEL_URL,
        metadata={"telegram_chat_id": str(chat_id)}
    )

    keyboard = [[InlineKeyboardButton("💳 Plătește acum", url=session.url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup)

# ---------------- RULEAZĂ ----------------
def run_flask():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    threading.Thread(target=check_expired_subscriptions, daemon=True).start()
    app_telegram = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app_telegram.add_handler(CommandHandler("start", start))
    app_telegram.run_polling()
