from flask import Flask, request
import requests
import json
import hmac
import hashlib

# 🔐 Cheia secretă Stripe Webhook
STRIPE_WEBHOOK_SECRET = 'whsec_1O4pbM0fh8addVmpd2fK4uifiQava33I'

# 🤖 Token Telegram Bot
TELEGRAM_BOT_TOKEN = '7718252241:AAHobde74C26V4RlRT1EW9n0Z0gIsZvrxcA'

# 📩 ID-ul tău personal de Telegram (George)
TELEGRAM_CHAT_ID = '8016135463'

# 🧠 Mesaj trimis la abonare
WELCOME_MESSAGE = (
    "✅ Abonamentul tău a fost confirmat cu succes!\n\n"
    "🎉 Bine ai venit în grupul privat ESCORTE-ROMÂNIA❌️❌️❌️.\n\n"
    "📎 Accesează grupul aici: https://t.me/+rxM_lgKEXw85OTBk\n\n"
    "⏳ Abonamentul este valabil 30 de zile. Mulțumim!"
)

# Inițializează aplicația Flask
app = Flask(__name__)

# 🔒 Verificare semnătură Stripe

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

# 🟢 Rulează aplicația Flask pe portul 10000
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
