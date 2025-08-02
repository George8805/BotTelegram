import stripe
import logging
from datetime import datetime, timedelta
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import threading
import json
import os
import secrets
import requests

# ---------------- CONFIG ----------------
TELEGRAM_TOKEN = "8285233635:AAEmE6IsunZ8AXVxJ2iVh5fa-mY0ppoKcgQ"
STRIPE_SECRET_KEY = "sk_test_51RmH5NCFUXMdgQRziwrLse45qn00G24mL7ZYt1aEwiB9wFCTJUNcw9g8YLnVZY3k0VyQAKJdmGI0bnWa4og8qfYG00uTJvHUMQ"
STRIPE_WEBHOOK_SECRET = "whsec_BBSUbBVkatYXc9SHUdQXPKFm5YhOE2fI"
PRODUCT_NAME = "Abonament Premium 30 zile"
PRICE_RON = 25
GROUP_ID = -1002577679941  # ID grup privat

stripe.api_key = STRIPE_SECRET_KEY

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- FIȘIER ABONAȚI ----------------
abonati_file = "abonati.json"
if not os.path.exists(abonati_file):
    with open(abonati_file, "w") as f:
        json.dump({}, f)

def load_abonati():
    with open(abonati_file, "r") as f:
        return json.load(f)

def save_abonati(data):
    with open(abonati_file, "w") as f:
        json.dump(data, f)

# ---------------- FUNCȚII LINK ----------------
def generate_invite_link():
    token = secrets.token_urlsafe(8)
    expire_date = datetime.now() + timedelta(hours=1)
    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/createChatInviteLink",
        json={
            "chat_id": GROUP_ID,
            "expire_date": int(expire_date.timestamp()),
            "member_limit": 1,
            "name": f"Access-{token}"
        }
    )
    data = r.json()
    return data.get("result", {}).get("invite_link")

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
            abonati = load_abonati()
            expiry_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
            abonati[str(chat_id)] = expiry_date
            save_abonati(abonati)

            link = generate_invite_link()
            if link:
                text = f"✅ Plata confirmată!\n📅 Abonament activ până la {expiry_date}\n\n🔗 Intră în grup aici: {link}"
            else:
                text = "✅ Plata confirmată, dar nu am putut genera linkul de acces."

            send_telegram_message(chat_id, text)

    return "✅ Webhook received", 200

def send_telegram_message(chat_id, text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    )

# ---------------- TELEGRAM BOT ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    abonati = load_abonati()

    if str(chat_id) in abonati:
        exp_date = datetime.strptime(abonati[str(chat_id)], "%Y-%m-%d %H:%M:%S")
        if exp_date > datetime.now():
            link = generate_invite_link()
            await update.message.reply_text(
                f"✅ Ai abonament activ până la {exp_date.strftime('%d.%m.%Y')}!\n🔗 Intră în grup aici: {link}"
            )
            return

    text = (
        "Bună,\n\n"
        "⭐ Aici veți găsi conținut premium și leaks.\n"
        f"⭐ Un abonament costă {PRICE_RON} RON pentru 30 de zile.\n"
        "⭐ Click pe butonul de mai jos pentru plată."
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
        success_url="https://t.me/EscorteRO1_bot",
        cancel_url="https://t.me/EscorteRO1_bot",
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
    app_telegram = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app_telegram.add_handler(CommandHandler("start", start))
    app_telegram.run_polling()
