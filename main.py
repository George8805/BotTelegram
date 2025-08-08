import stripe
import logging
from datetime import datetime
from flask import Flask, request
import requests, json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMemberUpdated
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, ChatMemberHandler
import threading

# ---------------- CONFIG (live) ----------------
TELEGRAM_TOKEN = "8285233635:AAEmE6IsunZ8AXVxJ2iVh5fa-mY0ppoKcgQ"

STRIPE_SECRET_KEY     = "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"
STRIPE_WEBHOOK_SECRET = "whsec_LxOkuricKYEikXru9KjQje65g4MNapK9"

GROUP_CHAT_ID = -1002577679941
INVITE_LINK   = "https://t.me/+rK1HDp49LEIyYmRk"    # link permanent
PRICE_ID      = "price_1RsNMwCFUXMdgQRzVlmVTBut"   # abonament lunar

stripe.api_key = STRIPE_SECRET_KEY

# chat_id -> subscription_id (cache în RAM)
active_subscriptions = {}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ---------------- HELPER ----------------
def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup  # JSON string
    requests.post(url, json=payload)

def add_user_to_group(user_id):
    # NU mai punem linkul în text; doar buton
    text = (
        "Bună,\n\n"
        "⭐ Aici veți găsi conținut premium și leaks, postat de mai multe modele din România și nu numai.\n\n"
        "⭐ Pentru a intra în grup, trebuie să vă abonați. Un abonament costă 25 RON pentru 30 de zile.\n\n"
        "⭐ Vă mulțumim că ați ales să fiți membru al grupului nostru!"
    )
    reply_markup = json.dumps({
        "inline_keyboard": [[
            {"text": "🔗 Intră în grup", "url": INVITE_LINK}
        ]]
    })
    send_message(user_id, text, reply_markup=reply_markup)

def remove_user_from_group(user_id):
    # remove fără ban (kick + unban)
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/kickChatMember",
            json={"chat_id": GROUP_CHAT_ID, "user_id": user_id, "until_date": int(datetime.now().timestamp()) + 60}
        )
    finally:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/unbanChatMember",
            json={"chat_id": GROUP_CHAT_ID, "user_id": user_id}
        )

def find_active_subscription_by_user(user_id: int):
    """Caută în Stripe un abonament activ care are metadata.telegram_chat_id == user_id."""
    try:
        res = stripe.Subscription.search(
            query=f"metadata['telegram_chat_id']:'{user_id}' AND status:'active'",
            limit=1,
        )
        if res and res.data:
            return res.data[0].id
    except Exception as e:
        logger.error(f"Stripe search error: {e}")
    return None

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
    obj = event["data"]["object"]
    logger.info(f"📢 Stripe event: {event_type}")

    def _cache(chat_id, subscription_id):
        if chat_id and subscription_id:
            active_subscriptions[int(chat_id)] = subscription_id
            logger.info(f"cache map {chat_id} -> {subscription_id}")

    # 1) Checkout inițial (subscription create)
    if event_type == "checkout.session.completed":
        chat_id = (obj.get("metadata") or {}).get("telegram_chat_id")
        subscription_id = obj.get("subscription")

        # Plasă de siguranță — scriem metadata pe subscription
        if subscription_id and chat_id:
            try:
                stripe.Subscription.modify(subscription_id, metadata={"telegram_chat_id": str(chat_id)})
            except Exception as e:
                logger.error(f"⚠️ Set metadata on sub failed: {e}")

        _cache(chat_id, subscription_id)
        if chat_id:
            add_user_to_group(int(chat_id))

    # 2) Reînnoire cu plată
    elif event_type == "invoice.payment_succeeded":
        subscription_id = obj.get("subscription")
        chat_id = (obj.get("metadata") or {}).get("telegram_chat_id")
        if not chat_id and subscription_id:
            try:
                sub = stripe.Subscription.retrieve(subscription_id)
                chat_id = (sub.get("metadata") or {}).get("telegram_chat_id")
            except Exception as e:
                logger.error(f"retrieve sub error: {e}")
        _cache(chat_id, subscription_id)
        if chat_id:
            add_user_to_group(int(chat_id))

    # 3) Neplată / anulare
    elif event_type in ("invoice.payment_failed", "customer.subscription.deleted"):
        subscription_id = obj.get("subscription") or obj.get("id")
        chat_id = (obj.get("metadata") or {}).get("telegram_chat_id")
        if not chat_id and subscription_id:
            try:
                sub = stripe.Subscription.retrieve(subscription_id)
                chat_id = (sub.get("metadata") or {}).get("telegram_chat_id")
            except Exception as e:
                logger.error(f"retrieve sub (fail/cancel) error: {e}")
        if chat_id:
            remove_user_from_group(int(chat_id))
            active_subscriptions.pop(int(chat_id), None)

    return "ok", 200

# ---------------- TELEGRAM: detect exit -> cancel sub ----------------
async def member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    old = update.chat_member.old_chat_member.status
    new = update.chat_member.new_chat_member.status
    if old in ("member", "administrator") and new == "left":
        user_id = update.chat_member.from_user.id
        logger.info(f"👋 {user_id} a ieșit din grup; încerc să anulez abonamentul")

        sub_id = active_subscriptions.get(user_id)
        if not sub_id:
            sub_id = find_active_subscription_by_user(user_id)

        if sub_id:
            try:
                stripe.Subscription.delete(sub_id)
                active_subscriptions.pop(user_id, None)
                logger.info(f"❌ Abonament {sub_id} anulat pentru {user_id}")
            except Exception as e:
                logger.error(f"⚠️ Anulare eșuată pentru {user_id}: {e}")
        else:
            logger.info("Nu am găsit abonament activ în Stripe pentru userul care a ieșit.")

# ---------------- TELEGRAM BOT ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # Creează sesiune nouă de fiecare dată + metadata pe session & subscription
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{"price": PRICE_ID, "quantity": 1}],
        mode="subscription",
        success_url="https://t.me/EscorteRO1_bot",
        cancel_url="https://t.me/EscorteRO1_bot",
        metadata={"telegram_chat_id": str(chat_id)},
        subscription_data={"metadata": {"telegram_chat_id": str(chat_id)}},
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

# ---------------- RUN ----------------
def run_flask():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    tg_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    tg_app.add_handler(CommandHandler("start", start))
    tg_app.add_handler(ChatMemberHandler(member_update, ChatMemberHandler.CHAT_MEMBER))
    tg_app.run_polling()
