import os
import time
import json
import hmac
import hashlib
from flask import Flask, request, abort
import requests
from threading import Thread

# Setări
BOT_TOKEN = os.getenv("BOT_TOKEN")
STRIPE_SECRET = os.getenv("STRIPE_SECRET")
TELEGRAM_GROUP_ID = os.getenv("TELEGRAM_GROUP_ID")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

app = Flask(__name__)
abonati = {}  # user_id: expire_timestamp

def trimite_mesaj(user_id, text):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={
        "chat_id": user_id,
        "text": text
    })

def adauga_in_grup(user_id):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/inviteChatMember", json={
        "chat_id": TELEGRAM_GROUP_ID,
        "user_id": user_id
    })

@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    try:
        event = json.loads(payload)
        if sig_header:
            expected_sig = hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected_sig, sig_header.split(',')[1].split('=')[1]):
                abort(400)

        if event['type'] == 'checkout.session.completed':
            metadata = event['data']['object']['metadata']
            user_id = int(metadata['telegram_id'])
            expire = int(time.time()) + 30 * 86400
            abonati[user_id] = expire
            adauga_in_grup(user_id)
            trimite_mesaj(user_id, "✅ Ai fost adăugat pentru 30 de zile.")
        return '', 200
    except Exception as e:
        print(e)
        return '', 400

@app.route("/start", methods=["GET"])
def start():
    return "Botul e pornit!"

def monitorizare_expirari():
    while True:
        acum = int(time.time())
        for user_id, expira in list(abonati.items()):
            if acum > expira:
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/kickChatMember", data={
                    "chat_id": TELEGRAM_GROUP_ID,
                    "user_id": user_id
                })
                del abonati[user_id]
        time.sleep(3600)

if __name__ == "__main__":
    Thread(target=monitorizare_expirari).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
