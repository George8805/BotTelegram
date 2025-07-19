from flask import Flask, request
import json
import requests
import hmac
import hashlib

app = Flask(__name__)

# 🔐 Cheia secretă Stripe Webhook
STRIPE_WEBHOOK_SECRET = 'whsec_1O4pbM0fh8addVmpd2fK4uifiQava33I'

# 🤖 Token Telegram Bot
TELEGRAM_BOT_TOKEN = '7718252241:AAHobde74C26V4RlRT1EW9n0Z0gIsZvrxcA'

# 📩 ID-ul tău personal de Telegram
TELEGRAM_CHAT_ID = '8016135463'

# 📎 Link public de plată Stripe
STRIPE_LINK = 'https://buy.stripe.com/bJedR836t0JB1C3dI3es001'

# 🔗 Linkul de invitație către canalul privat (intern)
TELEGRAM_INVITE_LINK = 'https://t.me/+rxM_lgKEXw85OTBk'

# 🧠 Mesaj trimis la abonare
WELCOME_MESSAGE = (
    "✅ Abonamentul tău a fost confirmat cu succes!\n\n"
    "🎉 Bine ai venit în grupul privat ESCORTE-ROMÂNIA❌️❌️❌️.\n\n"
    "📎 Accesează canalul de Telegram: {invite_link}\n\n"
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
def send_telegram_message(text, chat_id):
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

# 🎯 Webhook Stripe
@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature', '')

    if STRIPE_WEBHOOK_SECRET and not verify_stripe_signature(payload, sig_header):
        return 'Invalid signature', 400

    try:
        event = json.loads(payload)
        if event['type'] == 'checkout.session.completed':
            send_telegram_message(WELCOME_MESSAGE.format(invite_link=TELEGRAM_INVITE_LINK), TELEGRAM_CHAT_ID)
            return '', 200
    except Exception as e:
        print("Eroare în procesare:", e)
        return 'Error', 400

    return '', 200

# 📬 Webhook pentru Telegram
@app.route(f'/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
def telegram_webhook():
    data = request.get_json()
    if "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"]["text"]

        if text == "/start":
            send_telegram_message(
                f"Bun venit! Pentru acces în canal, plătește aici:\n{STRIPE_LINK}", chat_id
            )
    return '', 200

if __name__ == '__main__':
    app.run(port=10000)
