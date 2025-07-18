from flask import Flask, request
import json
import requests
import time
import hmac
import hashlib

app = Flask(__name__)

# 🔐 Cheia secretă Stripe Webhook
STRIPE_WEBHOOK_SECRET = 'whsec_IJjzBmzaddtcS7Qq55TWvgVRBhlLZwb7'

# 🤖 Token Telegram Bot
TELEGRAM_BOT_TOKEN = '7718252241:AAHobde74C26V4RlRT1EW9n0Z0gIsZvrxcA'

# 📩 ID-ul tău personal de Telegram
TELEGRAM_CHAT_ID = '8016135463'

# 📎 Link public de plată Stripe
STRIPE_LINK = 'https://buy.stripe.com/5kQfZggXj4ZR94vgUfes000'

# 🧠 Mesaj trimis la abonare
WELCOME_MESSAGE = (
    "✅ Abonamentul tău a fost confirmat cu succes!\n\n"
    "🎉 Bine ai venit în grupul privat ESCORTE-ROMÂNIA❌️❌️❌️.\n\n"
    "📎 Dacă nu ești deja în grup, contactează @EscorteRO_bot pentru acces.\n\n"
    "⏳ Abonamentul este valabil 30 de zile. Mulțumim!"
)

# ✅ Verificare semnătură Stripe
def verify_stripe_signature(payload, sig_header):
    expected_sig = hmac.new(
        STRIPE_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return expected_sig in sig_header

# 📩 Trimite mesaj pe Telegram
def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text
    }
    try:
        response = requests.post(url, json=data)
        print("Trimis pe Telegram:", response.text)
    except Exception as e:
        print("Eroare la trimitere Telegram:", e)

# 🎯 Endpoint-ul webhook Stripe
@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature', '')

    # Dacă semnătura nu e validă, ignorăm
    if STRIPE_WEBHOOK_SECRET and not verify_stripe_signature(payload, sig_header):
        return 'Invalid signature', 400

    try:
        event = json.loads(payload)

        if event['type'] == 'checkout.session.completed':
            send_telegram_message(WELCOME_MESSAGE)
            return '', 200

    except Exception as e:
        print("Eroare în procesare:", e)
        return 'Error', 400

    return '', 200

# 🔥 Pornim serverul pe 0.0.0.0:5000 pentru Render
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
