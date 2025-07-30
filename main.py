import os
import json
import stripe
import telegram
from flask import Flask, request, abort

app = Flask(__name__)

# Chei
stripe.api_key = "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"
endpoint_secret = "whsec_S7AvDmiroK8REpBwWljjHY6p6ZCIsLGV"
TELEGRAM_BOT_TOKEN = "8285233635:AAEmE6IsunZ8AXVxJ2iVh5fa-mY0ppoKcgQ"
CHAT_ID = "8016135463"

# Mesaj de bun venit
WELCOME_MESSAGE = (
    "\u2728 Bună,\n\n"
    "\u2b50 Aici veți găsi conținut premium și leaks, postat de mai multe modele din România și nu numai.\n\n"
    "\u2b50 Pentru a intra în grup, trebuie să vă abonați. Un abonament costă 25 pe pentru 30 de zile."
    " Pentru a vă abona, faceți clic pe butonul de mai jos.\n\n"
    "\u2b50 Vă mulțumim că ați ales să fiți membru al grupului nostru!"
)

# Trimite mesaj pe Telegram
bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
def send_telegram_message(text):
    bot.send_message(chat_id=CHAT_ID, text=text)

@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError as e:
        return "Invalid signature", 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        send_telegram_message(
            f"\u2705 Plata finalizată! Accesul a fost activat pentru 30 de zile.\n\nDetalii: {session['customer_email']}"
        )

    return "", 200

if __name__ == "__main__":
    app.run(port=5000)
