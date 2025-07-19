from flask import Flask, request
import json
import requests
import hmac
import hashlib

app = Flask(__name__)

# 🔐 Stripe webhook secret
STRIPE_WEBHOOK_SECRET = 'whsec_IJjzBmzaddtcS7Qq55TWvgVRBhlLZwb7'

# 🤖 Telegram Bot Token
TELEGRAM_BOT_TOKEN = '7718252241:AAHobde74C26V4RlRT1EW9n0Z0gIsZvrxcA'

# 👤 Chat ID al administratorului (pentru notificări opționale)
ADMIN_CHAT_ID = '8016135463'

# 📎 Linkul de plată Stripe
STRIPE_PAYMENT_LINK = 'https://buy.stripe.com/bJedR836t0JB1C3dI3es001'

# 🔗 Link de invitație Telegram (NEAFIȘAT în mesaj)
TELEGRAM_INVITE_LINK = 'https://t.me/+rxM_lgKEXw85OTBk'

# 🧠 Mesaj personalizat la abonare
WELCOME_MESSAGE = (
    "✅ Plata a fost confirmată cu succes!\n\n"
    "🎉 Bine ai venit în grupul privat ESCORTE-ROMÂNIA❌️❌️❌️.\n\n"
    "⏳ Abonamentul tău este valabil 30 de zile. Mulțumim!"
)

# ✅ Verificare semnătură Stripe

def verify_stripe_signature(payload, sig_header):
    expected_sig = hmac.new(
        STRIPE_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return expected_sig in sig_header

# 📩 Trimite mesaj prin Telegram

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text
    }
    try:
        response = requests.post(url, json=data)
        print("Trimis pe Telegram:", response.text)
    except Exception as e:
        print("Eroare la trimitere Telegram:", e)

# 🎯 Webhook pentru Stripe

@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature', '')

    if STRIPE_WEBHOOK_SECRET and not verify_stripe_signature(payload, sig_header):
        return 'Invalid signature', 400

    try:
        event = json.loads(payload)

        if event['type'] == 'checkout.session.completed':
            # Trimitere mesaj de bun venit și folosirea internă a linkului de invitație
            send_telegram_message(ADMIN_CHAT_ID, WELCOME_MESSAGE)

            # Se poate extinde cu adăugare automată dacă ai un bot cu acces de admin în canal

            return '', 200

    except Exception as e:
        print("Eroare în procesare:", e)
        return 'Error', 400

    return '', 200

# Pornire server Flask
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
