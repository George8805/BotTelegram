import os
import json
import stripe
import requests
from flask import Flask, request, abort

app = Flask(__name__)

# Setări din variabile de mediu (sau hardcodate dacă e test local)
TELEGRAM_BOT_TOKEN = "7718252241:AAHobde74C26V4RlRT1EW9n0Z0gIsZvrxcA"
STRIPE_SECRET_KEY = "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"
STRIPE_WEBHOOK_SECRET = "whsec_1O4pbM0fh8addVmpd2fK4uifiQava33I"
TELEGRAM_CHAT_ID = "8016135463"
TELEGRAM_CHANNEL_LINK = "https://t.me/+rxM_lgKEXw85OTBk"

stripe.api_key = STRIPE_SECRET_KEY

# Mesajul trimis la /start
START_MESSAGE = (
    "👋 Bun venit!\n\n"
    "📌 Pentru a avea acces la canalul premium ESCORTE-ROMÂNIA, este necesar un abonament de 25 RON pentru 30 de zile.\n\n"
    "💳 Folosește linkul de mai jos pentru a efectua plata:\n"
    "👉 https://buy.stripe.com/bJedR836t0JB1C3dI3es001\n\n"
    "✅ După plată, accesul îți va fi acordat automat."
)

# Trimite mesaj pe Telegram
def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

# Adaugă utilizator în canalul privat (fără a trimite linkul)
def add_user_to_channel(user_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/inviteChatMember"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_LINK,
        "user_id": user_id
    }
    requests.post(url, json=payload)

# Endpoint pentru comenzi Telegram (/start)
@app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    data = request.json
    message = data.get("message")
    if message:
        chat_id = message["chat"]["id"]
        text = message.get("text")
        if text == "/start":
            send_telegram_message(chat_id, START_MESSAGE)
    return "", 200

# Endpoint Stripe webhook
@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        print("Webhook error:", str(e))
        return "", 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        metadata = session.get("metadata", {})
        chat_id = metadata.get("telegram_chat_id")

        if chat_id:
            add_user_to_channel(int(chat_id))
            send_telegram_message(chat_id, "✅ Abonamentul tău a fost confirmat! Ai fost adăugat în canalul premium. Accesul este valabil 30 de zile.")

    return "", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
