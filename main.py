from flask import Flask, request
import json
import requests
import time
import hmac
import hashlib

app = Flask(__name__)

# 🔐 Cheia secretă Stripe Webhook
STRIPE_WEBHOOK_SECRET = 'whsec_1O4pbM0fh8addVmpd2fK4uifiQava33I'

# 🤖 Token Telegram Bot
TELEGRAM_BOT_TOKEN = '7718252241:AAHobde74C26V4RlRT1EW9n0Z0gIsZvrxcA'

# 📩 ID-ul tău personal de Telegram (adminul)
TELEGRAM_ADMIN_CHAT_ID = '8016135463'

# 📎 Link public de plată Stripe (pentru redirect din mesajul /start)
STRIPE_PAYMENT_LINK = 'https://buy.stripe.com/bJedR836t0JB1C3dI3es001'

# 🔗 Link de invitație către canalul privat (NEAFIȘAT PUBLIC)
TELEGRAM_INVITE_LINK = 'https://t.me/+rxM_lgKEXw85OTBk'

# 🧠 Mesaj trimis după comandă /start
WELCOME_TEXT = (
    "👋 Bun venit!\n\n"
    "📸 Aici veți găsi conținut premium și leaks postate de mai multe modele din România și nu numai.\n\n"
    "💳 Pentru a intra în grupul privat, achită abonamentul (25 lei / 30 zile) folosind butonul de mai jos:\n"
    f"{STRIPE_PAYMENT_LINK}\n\n"
    "✅ După confirmarea plății, vei primi acces automat în canal."
)

# ✅ Verificare semnătură Stripe

def verify_stripe_signature(payload, sig_header):
    expected_sig = hmac.new(
        STRIPE_WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return expected_sig in sig_header

# 📩 Trimite mesaj pe Telegram

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text
    }
    try:
        requests.post(url, json=data)
    except Exception as e:
        print("Eroare trimitere mesaj:", e)

# ➕ Adaugă utilizator în canal prin link (trimis privat)

def send_invite_after_payment():
    message = (
        "✅ Plata a fost confirmată!\n\n"
        "📥 Click pe linkul de mai jos pentru a intra în canal:\n"
        f"{TELEGRAM_INVITE_LINK}"
    )
    send_telegram_message(TELEGRAM_ADMIN_CHAT_ID, message)

# 🔄 Răspunde la comanda /start din Telegram
@app.route(f"/bot{TELEGRAM_BOT_TOKEN}", methods=['POST'])
def telegram_webhook():
    data = request.get_json()
    if 'message' in data:
        chat_id = data['message']['chat']['id']
        text = data['message'].get('text', '')

        if text == "/start":
            send_telegram_message(chat_id, WELCOME_TEXT)

    return '', 200

# 🎯 Endpoint webhook Stripe
@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature', '')

    if STRIPE_WEBHOOK_SECRET and not verify_stripe_signature(payload, sig_header):
        return 'Invalid signature', 400

    try:
        event = json.loads(payload)
        if event['type'] == 'checkout.session.completed':
            send_invite_after_payment()
            return '', 200

    except Exception as e:
        print("Stripe Error:", e)
        return 'Error', 400

    return '', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
