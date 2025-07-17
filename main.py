from flask import Flask, request
import stripe
import requests
import os

app = Flask(__name__)

# Variabile de configurare – înlocuiește cu valorile tale reale
TELEGRAM_BOT_TOKEN = "TOKENUL_TAU_TELEGRAM"
TELEGRAM_CHAT_ID = "CHAT_ID_UL_TAU"  # sau îl extragem din update
STRIPE_SECRET = "sk_test_XXXX..."  # cheia ta Stripe (test)
ENDPOINT_SECRET = "whsec_XXXX..."  # semnătura webhook Stripe

stripe.api_key = STRIPE_SECRET

@app.route("/")
def index():
    return "Bot Telegram + Stripe este online!"

@app.route("/webhook", methods=["POST"])
def webhook_received():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, ENDPOINT_SECRET)
    except stripe.error.SignatureVerificationError:
        return "Semnătura Stripe invalidă", 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        mesaj = f"✅ Plată nouă de la {session.get('customer_email')} — suma: {session['amount_total'] / 100:.2f} {session['currency'].upper()}"
        send_telegram_message(mesaj)

    return "OK", 200

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text
    }
    requests.post(url, data=payload)

if __name__ == "__main__":
    app.run(debug=True)
