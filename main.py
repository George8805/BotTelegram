from flask import Flask, request, jsonify
import requests
import hmac
import hashlib
import os

app = Flask(__name__)

# === Configurare ===
BOT_TOKEN = "7718252241:AAHobde74C26V4RlRT1EW9n0Z0gIsZvrxcA"
CHAT_ID = "8016135463"
WEBHOOK_SECRET = "whsec_WHN49X87H31jMtKEwGh01GrIhJoWu1wo"

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    requests.post(url, data=payload)

@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    # ✅ Verificare semnătură
    try:
        event = request.get_json()
    except Exception as e:
        return jsonify({"error": "Invalid payload"}), 400

    if event.get("type") == "checkout.session.completed":
        session = event["data"]["object"]
        email = session.get("customer_email", "Fără email")
        amount = session.get("amount_total", 0) / 100

        message = f"✅ <b>Plată Stripe confirmată</b>\n\n👤 Email: {email}\n💸 Suma: {amount:.2f} EUR"
        send_telegram(message)

    return jsonify({"status": "received"}), 200

if __name__ == "__main__":
    app.run(port=5000)
