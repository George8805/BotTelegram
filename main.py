import stripe
import logging
from datetime import datetime, timedelta
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import threading
import requests
import time

# ---------------- CONFIG ----------------
TELEGRAM_TOKEN = "8285233635:AAEmE6IsunZ8AXVxJ2iVh5fa-mY0ppoKcgQ"
STRIPE_SECRET_KEY = "sk_test_51RmH5NCFUXMdgQRziwrLse45qn00G24mL7ZYt1aEwiB9wFCTJUNcw9g8YLnVZY3k0VyQAKJdmGI0bnWa4og8qfYG00uTJvHUMQ"
STRIPE_WEBHOOK_SECRET = "whsec_S7AvDmiroK8REpBwWljjHY6p6ZCIsLGV"

PRODUCT_NAME = "Abonament Premium 30 zile"
PRICE_RON = 25  # în RON
SUCCESS_URL = "https://t.me/numele_botului"
CANCEL_URL = "https://t.me/numele_botului"

# ID-ul grupului (îl afli cu /id din grup)
GROUP_CHAT_ID = -1001234567890  # schimbă cu chat_id-ul real al grupului tău

stripe.api_key = STRIPE_SECRET_KEY

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- FLASK APP PENTRU STRIPE WEBHOOK ----------------
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
            expiry_date = datetime.now() + timedelta(days=30)
            confirm_text = (
                f"✅ Plata ta a fost confirmată!\n\n"
                f"📅 Abonamentul tău este activ până la **{expiry_date.strftime('%d.%m.%Y')}**."
            )
            send_telegram_message(chat_id, confirm_text)

            # Creăm link unic pentru grup
            invite_link = create_group_invite_link()
            if invite_link:
                send_telegram_message(chat_id, f"🔗 Intră în grup folosind acest link (valabil 1 oră / 1 utilizare):\n{invite_link}")

    return "✅ Webhook received", 200

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def create_group_invite_link():
    expire_time = int(time.time()) + 3600  # 1 oră
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

# ---------------- COMANDA /id ----------------
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"📌 Chat ID: `{chat_id}`", parse_mode="Markdown")

# ---------------- COMANDA /start ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (
        "Bună,\n\n"
        "⭐ Aici veți găsi conținut premium și leaks, postat de mai multe modele din România și nu numai.\n"
        "⭐ Pentru a intra în grup, trebuie să vă abonați. Un abonament costă 25 RON pentru 30 de zile.\n"
        "⭐ Pentru a vă abona, faceți clic pe butonul de mai jos.\n"
        "⭐ Vă mulțumim că ați ales să fiți membru al grupului nostru!"
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

# ---------------- RULEAZĂ TELEGRAM BOT + FLASK ----------------
def run_flask():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    app_telegram = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app_telegram.add_handler(CommandHandler("start", start))
    app_telegram.add_handler(CommandHandler("id", get_id))
    app_telegram.run_polling()
