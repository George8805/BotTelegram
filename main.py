import stripe
import logging
import json
import os
from datetime import datetime, timedelta
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import threading
import requests
import time

# ---------------- CONFIG ----------------
TELEGRAM_TOKEN = "TOKEN_BOT"
STRIPE_SECRET_KEY = "sk_test_CHEIA_TA"
STRIPE_WEBHOOK_SECRET = "whsec_CHEIA_TA"
GROUP_CHAT_ID = -1002577679941  # ID-ul grupului tău

PRODUCT_NAME = "Abonament Premium 30 zile"
PRICE_RON = 25
SUCCESS_URL = "https://t.me/numele_botului"
CANCEL_URL = "https://t.me/numele_botului"
ABONAMENTE_FILE = "abonamente.json"

stripe.api_key = STRIPE_SECRET_KEY

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- FUNCȚII UTILE ----------------
def load_abonamente():
    if not os.path.exists(ABONAMENTE_FILE):
        return {}
    with open(ABONAMENTE_FILE, "r") as f:
        return json.load(f)

def save_abonamente(data):
    with open(ABONAMENTE_FILE, "w") as f:
        json.dump(data, f, indent=4)

def abonament_activ(chat_id):
    abonamente = load_abonamente()
    if str(chat_id) in abonamente:
        expira_str = abonamente[str(chat_id)]
        expira = datetime.strptime(expira_str, "%Y-%m-%d %H:%M:%S")
        return expira > datetime.now()
    return False

def seteaza_abonament(chat_id):
    abonamente = load_abonamente()
    expira = datetime.now() + timedelta(days=30)
    abonamente[str(chat_id)] = expira.strftime("%Y-%m-%d %H:%M:%S")
    save_abonamente(abonamente)
    return expira

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

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

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
            # Activează abonament
            expira = seteaza_abonament(chat_id)
            confirm_text = (
                f"✅ Plata confirmată!\n\n"
                f"📅 Abonamentul tău este activ până la **{expira.strftime('%d.%m.%Y')}**."
            )
            send_telegram_message(chat_id, confirm_text)

            # Creează link unic și trimite
            invite_link = create_group_invite_link()
            if invite_link:
                send_telegram_message(chat_id, f"🔗 Intră în grup (link unic, valabil 1 oră / 1 utilizare):\n{invite_link}")

    return "✅ Webhook received", 200

# ---------------- COMANDA /id ----------------
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"📌 Chat ID: `{chat_id}`", parse_mode="Markdown")

# ---------------- COMANDA /start ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # Dacă are abonament activ → trimite direct link unic
    if abonament_activ(chat_id):
        invite_link = create_group_invite_link()
        if invite_link:
            await update.message.reply_text(f"🔗 Abonament activ!\nIntră în grup:\n{invite_link}")
        else:
            await update.message.reply_text("⚠️ Eroare creare link!")
        return

    # Altfel → oferă plată
    text = (
        "Bună,\n\n"
        "⭐ Aici vei găsi conținut premium și leaks.\n"
        f"⭐ Abonament: {PRICE_RON} RON pentru 30 zile.\n"
        "⭐ Click pe buton pentru a plăti."
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

# ---------------- RULEAZĂ BOT + FLASK ----------------
def run_flask():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    app_telegram = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app_telegram.add_handler(CommandHandler("start", start))
    app_telegram.add_handler(CommandHandler("id", get_id))
    app_telegram.run_polling()
