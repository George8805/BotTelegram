import stripe
import logging
from datetime import datetime, timedelta
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import threading
import requests
import time
import json
import os 

# ---------------- CONFIG ----------------
TELEGRAM_TOKEN = "8285233635:AAEmE6IsunZ8AXVxJ2iVh5fa-mY0ppoKcgQ"
STRIPE_SECRET_KEY = "sk_test_51RmH5NCFUXMdgQRziwrLse45qn00G24mL7ZYt1aEwiB9wFCTJUNcw9g8YLnVZY3k0VyQAKJdmGI0bnWa4og8qfYG00uTJvHUMQ"
STRIPE_WEBHOOK_SECRET = "whsec_S7AvDmiroK8REpBwWljjHY6p6ZCIsLGV"
PRODUCT_NAME = "Abonament Premium 30 zile"
PRICE_RON = 25
SUCCESS_URL = "https://t.me/+rxM_lgKEXw85OTBk"
CANCEL_URL = "https://t.me/+rxM_lgKEXw85OTBk"

# ID grup Telegram
GROUP_CHAT_ID = -1001234567890  # pune ID-ul real al grupului

# Fisier pentru stocarea abonamentelor
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
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def create_invite_link():
    expire_time = int(time.time()) + 300  # 5 minute
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/createChatInviteLink"
    payload = {
        "chat_id": GROUP_CHAT_ID,
        "expire_date": expire_time,
        "member_limit": 1
    }
    r = requests.post(url, json=payload)
    if r.status_code == 200 and r.json().get("ok"):
        return r.json()["result"]["invite_link"]
    else:
        logger.error(f"Eroare creare link: {r.text}")
        return None

def remove_user_from_group(user_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/kickChatMember"
    payload = {
        "chat_id": GROUP_CHAT_ID,
        "user_id": user_id
    }
    requests.post(url, json=payload)

# ---------------- FLASK APP ----------------
app = Flask(__name__)

@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        return f"⚠️ Webhook error: {str(e)}", 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        chat_id = session.get("metadata", {}).get("telegram_chat_id")

        if chat_id:
            expiry_date = datetime.now() + timedelta(minutes=1)
            subs = load_subscriptions()
            subs[str(chat_id)] = {
                "expiry": expiry_date.strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": chat_id
            }
            save_subscriptions(subs)

            text = (
                f"✅ Plata confirmată!\n\n"
                f"📅 Abonamentul tău este activ până la **{expiry_date.strftime('%d.%m.%Y')}**."
            )
            send_telegram_message(chat_id, text)

            invite_link = create_invite_link()
            if invite_link:
                send_telegram_message(chat_id, f"🔗 Intră în grup aici (valabil 5 minute / 1 utilizare):\n{invite_link}")

    return "✅ Webhook received", 200

# ---------------- TELEGRAM BOT ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (
        "Bună,\n\n"
        "⭐ Aici vei găsi conținut premium.\n"
        f"⭐ Abonament: {PRICE_RON} RON / 30 zile.\n"
        "⭐ Apasă pe buton pentru a plăti."
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

# ---------------- JOB DE VERIFICARE ----------------
def check_expired_subscriptions():
    while True:
        subs = load_subscriptions()
        changed = False
        for chat_id, data in list(subs.items()):
            expiry = datetime.strptime(data["expiry"], "%Y-%m-%d %H:%M:%S")
            if datetime.now() > expiry:
                try:
                    remove_user_from_group(int(chat_id))
                    send_telegram_message(chat_id, "❌ Abonamentul tău a expirat. Pentru a reveni, plătește din nou.")
                except Exception as e:
                    logger.error(f"Eroare la eliminare utilizator {chat_id}: {e}")
                del subs[chat_id]
                changed = True
        if changed:
            save_subscriptions(subs)
        time.sleep(3600)  # verifică la fiecare oră

# ---------------- RULEAZĂ ----------------
def run_flask():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    threading.Thread(target=check_expired_subscriptions, daemon=True).start()
    app_telegram = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app_telegram.add_handler(CommandHandler("start", start))
    app_telegram.run_polling()
