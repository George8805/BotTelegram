import os
import json
import requests
from flask import Flask, request, abort
import stripe

# ====== CONFIGURARE ======
TELEGRAM_BOT_TOKEN = "7718252241:AAHobde74C26V4RlRT1EW9n0Z0gIsZvrxcA"
STRIPE_SECRET_KEY = "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"
STRIPE_WEBHOOK_SECRET = "whsec_1O4pbM0fh8addVmpd2fK4uifiQava33I"
PRIVATE_CHANNEL_ID = "@ESCORTE_ROMANIA"
RESTRICTED_CHAT_ID = -1002147483647  # înlocuiește dacă e nevoie
CHAT_ID_AUTORIZAT = [8016135463]  # ID-ul persoanei care trebuie adăugată

stripe.api_key = STRIPE_SECRET_KEY

app = Flask(__name__)

# ====== TRIMITE MESAJ TELEGRAM ======
def send_telegram_message(chat_id, text):
    url = "https://api.telegram.org/bot{}/sendMessage".format(TELEGRAM_BOT_TOKEN)
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

# ====== ADAUGĂ UTILIZATOR ÎN GRUP ======
def add_user_to_channel(user_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/inviteChatMember"
    payload = {
        "chat_id": PRIVATE_CHANNEL_ID,
        "user_id": user_id
    }
    response = requests.post(url, json=payload)
    return response.json()

# ====== ENDPOINT STRIPE WEBHOOK ======
@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("stripe-signature")
    event = None

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        abort(400)
    except stripe.error.SignatureVerificationError:
        abort(400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_email = session.get("customer_email")
        # ==========================
        for chat_id in CHAT_ID_AUTORIZAT:
            send_telegram_message(chat_id, "✅ Abonamentul tău a fost confirmat cu succes! Accesul tău va fi activ timp de 30 de zile.")
            add_user_to_channel(chat_id)

    return ("", 200)

# ====== BOT TELEGRAM BASIC ======
@app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    if "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"]["text"].strip().lower()
        if text == "/start":
            send_telegram_message(chat_id, "👋 Bun venit! Pentru a accesa grupul, finalizează plata prin linkul: https://buy.stripe.com/bJedR836t0JB1C3dI3")
    return ("", 200)

# ====== RUN LOCALLY ======
if __name__ == "__main__":
    app.run(port=10000)
