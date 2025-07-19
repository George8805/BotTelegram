
from flask import Flask, request
import json
import requests
import hmac
import hashlib

app = Flask(__name__)

# 🔐 Stripe Webhook Secret
STRIPE_WEBHOOK_SECRET = 'whsec_1O4pbM0fh8addVmpd2fK4uifiQava33I'

# 🤖 Telegram Bot Token
TELEGRAM_BOT_TOKEN = '7718252241:AAHobde74C26V4RlRT1EW9n0Z0gIsZvrxcA'

# 🧑 Chat ID-ul tău personal
TELEGRAM_CHAT_ID = '8016135463'

# 🎯 Link de plată Stripe
STRIPE_LINK = 'https://buy.stripe.com/bJedR836t0JB1C3dI3es001'

# 🔗 Link de invitație către canal (nu va fi afișat, doar folosit intern)
TELEGRAM_INVITE_LINK = 'https://t.me/+rxM_lgKEXw85OTBk'

# 📩 Mesaj trimis pe Telegram după plată
WELCOME_MESSAGE = (
    "✅ Abonamentul tău a fost confirmat cu succes!

"
    "🎉 Bine ai venit în grupul ESCORTE-ROMÂNIA❌️❌️❌️.

"
    "🔗 Apasă aici pentru a intra în canalul privat: " + TELEGRAM_INVITE_LINK + "\n\n"
    "⏳ Abonamentul este valabil 30 de zile. Mulțumim!"
)

def verify_stripe_signature(payload, sig_header):
    expected_sig = hmac.new(
        STRIPE_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return expected_sig in sig_header

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        requests.post(url, json=data)
    except Exception as e:
        print("Eroare la trimitere Telegram:", e)

@app.route("/")
def index():
    return "Bot ESCORTE-ROMÂNIA este activ."

@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")
    if STRIPE_WEBHOOK_SECRET and not verify_stripe_signature(payload, sig_header):
        return "Invalid signature", 400
    try:
        event = json.loads(payload)
        if event.get("type") == "checkout.session.completed":
            send_telegram_message(WELCOME_MESSAGE)
    except Exception as e:
        print("Eroare webhook:", e)
        return "Error", 400
    return "", 200
