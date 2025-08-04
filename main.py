import stripe
import logging
from datetime import datetime
from flask import Flask, request
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMemberUpdated
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, ChatMemberHandler
import threading

# ---------------- CONFIG ----------------
TELEGRAM_TOKEN = "8285233635:AAEmE6IsunZ8AXVxJ2iVh5fa-mY0ppoKcgQ"

# Stripe Live Keys
STRIPE_SECRET_KEY = "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"
STRIPE_WEBHOOK_SECRET = "whsec_LxOkuricKYEikXru9KjQje65g4MNapK9"

GROUP_CHAT_ID = -1002577679941  # Grup ESCORTE-ROMÂNIA❌️❌️❌️
INVITE_LINK = "https://t.me/+rK1HDp49LEIyYmRk"  # Link permanent de grup
PRICE_ID = "price_1RsNMwCFUXMdgQRzVlmVTBut"  # Price ID Live

stripe.api_key = STRIPE_SECRET_KEY

# Mapare chat_id → subscription_id (memorie RAM, reset la restart server)
active_subscriptions = {}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ---------------- HELPER FUNCTIONS ----------------

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

def add_user_to_group(user_id):
    mesaj_intampinare = (
        "Bună,\n\n"
        "⭐ Aici veți găsi conținut premium și leaks, postat de mai multe modele din România și nu numai.\n\n"
        "⭐ Pentru a intra în grup, trebuie să vă abonați. Un abonament costă 25 RON pentru 30 de zile.\n\n"
        "⭐ Vă mulțumim că ați ales să fiți membru al grupului nostru!\n\n"
        f"🔗 Intră în grup aici: {INVITE_LINK}"
    )
    send_message(user_id, mesaj_intampinare)

def remove_user_from_group(user_id):
    kick_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/kickChatMember"
    requests.post(kick_url, json={
        "chat_id": GROUP_CHAT_ID,
        "user_id": user_id,
        "until_date": int(datetime.now().timestamp()) + 60
    })
    unban_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/unbanChatMember"
    requests.post(unban_url, json={
        "chat_id": GROUP_CHAT_ID,
        "user_id": user_id
    })

# ---------------- STRIPE WEBHOOK ----------------

@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        return f"⚠️ Webhook error: {str(e)}", 400

    event_type = event["type"]
    data = event["data"]["object"]

    logger.info(f"📢 Event primit: {event_type}")

    # Plata inițială sau reînnoire
    if event_type == "checkout.session.completed":
        chat_id = data.get("metadata", {}).get("telegram_chat_id")
        subscription_id = data.get("subscription")
        if chat_id and subscription_id:
            active_subscriptions[int(chat_id)] = subscription_id
            add_user_to_group(int(chat_id))

    elif event_type == "invoice.payment_succeeded":
        subscription_id = data.get("subscription")
        chat_id = data.get("metadata", {}).get("telegram_chat_id")
        if chat_id and subscription_id:
            active_subscriptions[int(chat_id)] = subscription_id
            add_user_to_group(int(chat_id))

    # Plata eșuată sau abonament anulat
    elif event_type in ["invoice.payment_failed", "customer.subscription.deleted"]:
        chat_id = data.get("metadata", {}).get("telegram_chat_id")
        if chat_id:
            remove_user_from_group(int(chat_id))
            active_subscriptions.pop(int(chat_id), None)

    return "✅ Webhook received", 200

# ---------------- DETECTARE IEȘIRE DIN GRUP ----------------

async def member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.chat_member.old_chat_member.status in ["member", "administrator"] and \
       update.chat_member.new_chat_member.status == "left":
        user_id = update.chat_member.from_user.id
        logger.info(f"👋 {user_id} a ieșit singur din grup")

        # Dacă are abonament activ în memorie → anulăm în Stripe
        if user_id in active_subscriptions:
            sub_id = active_subscriptions[user_id]
            try:
                stripe.Subscription.delete(sub_id)
                logger.info(f"❌ Abonament {sub_id} anulat pentru user {user_id}")
                active_subscriptions.pop(user_id, None)
            except Exception as e:
                logger.error(f"⚠️ Eroare la anularea abonamentului: {e}")

# ---------------- TELEGRAM BOT ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # Creează sesiunea Stripe pentru abonament lunar
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{"price": PRICE_ID, "quantity": 1}],
        mode="subscription",
        success_url="https://t.me/EscorteRO1_bot",
        cancel_url="https://t.me/EscorteRO1_bot",
        metadata={"telegram_chat_id": str(chat_id)}
    )

    keyboard = [[InlineKeyboardButton("💳 Plătește abonamentul lunar", url=session.url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Bună,\n\n"
        "⭐ Aici veți găsi conținut premium și leaks, postat de mai multe modele din România și nu numai.\n"
        "⭐ Pentru a intra în grup, trebuie să vă abonați. Un abonament costă 25 RON pentru 30 de zile.\n"
        "⭐ Pentru a vă abona, faceți clic pe butonul de mai jos.\n"
        "⭐ Vă mulțumim că ați ales să fiți membru al grupului nostru!",
        reply_markup=reply_markup
    )

# ---------------- RUN BOTH ----------------

def run_flask():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    app_telegram = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app_telegram.add_handler(CommandHandler("start", start))
    app_telegram.add_handler(ChatMemberHandler(member_update, ChatMemberHandler.CHAT_MEMBER))
    app_telegram.run_polling()
