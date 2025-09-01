# app.py
import logging
import threading
from datetime import datetime

import requests
import stripe
from flask import Flask, request, redirect

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatMemberUpdated,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ChatMemberHandler,
)

# ---------------- CONFIG ----------------
TELEGRAM_TOKEN = "8285233635:AAG5-aJyEPaqK4P5LNMyN9FwOIgOG6HSjHw"

STRIPE_SECRET_KEY = "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"
STRIPE_WEBHOOK_SECRET = "whsec_LxOkuricKYEikXru9KjQje65g4MNapK9"

GROUP_CHAT_ID = -1002577679941
INVITE_LINK = "https://t.me/+rK1HDp49LEIyYmRk"
PRICE_ID = "price_1RsNMwCFUXMdgQRzVlmVTBut"

PUBLIC_BASE_URL = "https://bottelegram-0kpv.onrender.com"

stripe.api_key = STRIPE_SECRET_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("escorte-bot")

app = Flask(__name__)
active_subscriptions: dict[int, str] = {}

# ---------------- Redirect ----------------
@app.route("/join")
def join_group():
    return redirect(INVITE_LINK, code=302)

# ---------------- Helpers ----------------
def tg_send(chat_id: int, text: str, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
        "parse_mode": "HTML",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup.to_dict()
    requests.post(url, json=payload, timeout=10)

def add_user_flow(user_id: int):
    text = (
        "Bună,\n\n"
        "⭐ Aici veți găsi conținut premium și leaks, postat de mai multe modele din România și nu numai.\n\n"
        "⭐ Pentru a intra în grup, trebuie să vă abonați. Un abonament costă 25 RON pentru 30 de zile.\n\n"
        "⭐ Vă mulțumim că ați ales să fiți membru al grupului nostru!"
    )
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔗 Intră în grup", url=f"{PUBLIC_BASE_URL}/join")]]
    )
    tg_send(user_id, text, kb)

def remove_user_from_group(user_id: int):
    # kick (ban temporar 60s) + unban pentru a permite re-intrarea pe link
    kick_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/kickChatMember"
    requests.post(
        kick_url,
        json={
            "chat_id": GROUP_CHAT_ID,
            "user_id": user_id,
            "until_date": int(datetime.now().timestamp()) + 60,
        },
        timeout=10,
    )
    unban_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/unbanChatMember"
    requests.post(
        unban_url,
        json={"chat_id": GROUP_CHAT_ID, "user_id": user_id},
        timeout=10,
    )

def cancel_stripe_subscription_for_chat(chat_id: int):
    """Anulează abonamentul și oprește facturarea viitoare, pe baza metadata.telegram_chat_id."""
    try:
        query = f"metadata['telegram_chat_id']:'{chat_id}' AND status:'active'"
        page = stripe.Subscription.search(query=query, limit=1)
        if page and page.data:
            sub = page.data[0]
            # Anulare imediată
            stripe.Subscription.delete(sub.id)
            logger.info(f"Abonament {sub.id} ANULAT pentru chat {chat_id}")
            active_subscriptions.pop(chat_id, None)
            return True
        logger.info(f"Niciun abonament activ găsit pentru chat {chat_id}")
    except Exception as e:
        logger.exception(f"Eroare la anularea abonamentului: {e}")
    return False

def _get_chat_id_from_subscription(subscription_id: str) -> int | None:
    """Helper: extrage telegram_chat_id din metadata subscription-ului."""
    try:
        sub = stripe.Subscription.retrieve(subscription_id)
        meta = (sub.get("metadata") or {})
        chat_id_str = meta.get("telegram_chat_id")
        if chat_id_str:
            return int(chat_id_str)
    except Exception as e:
        logger.warning(f"Nu pot citi metadata din subscription {subscription_id}: {e}")
    return None

def _get_chat_id_from_customer(customer_id: str) -> int | None:
    """Fallback: extrage telegram_chat_id din metadata Customer-ului."""
    try:
        cust = stripe.Customer.retrieve(customer_id)
        meta = (cust.get("metadata") or {})
        chat_id_str = meta.get("telegram_chat_id")
        if chat_id_str:
            return int(chat_id_str)
    except Exception as e:
        logger.warning(f"Nu pot citi metadata din customer {customer_id}: {e}")
    return None

# ---------------- Stripe webhook ----------------
@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        logger.warning(f"Webhook verify failed: {e}")
        return "bad signature", 400

    etype = event["type"]
    obj = event["data"]["object"]
    logger.info(f"Stripe event: {etype}")

    if etype == "checkout.session.completed":
        # Legăm ferm atât SUBSCRIPTION cât și CUSTOMER de chat_id-ul UTILIZATORULUI
        chat_id = obj.get("metadata", {}).get("telegram_chat_id")
        subscription_id = obj.get("subscription")
        customer_id = obj.get("customer")

        if chat_id:
            # 1) atașează pe Customer (ca să-l vezi în Dashboard și ca fallback la evenimente)
            if customer_id:
                try:
                    stripe.Customer.modify(
                        customer_id,
                        metadata={"telegram_chat_id": str(chat_id)},
                    )
                except Exception as e:
                    logger.warning(f"Nu am putut seta metadata pe customer {customer_id}: {e}")

            # 2) atașează pe Subscription (sursa principală de adevăr)
            if subscription_id:
                try:
                    stripe.Subscription.modify(
                        subscription_id,
                        metadata={"telegram_chat_id": str(chat_id)},
                    )
                except Exception as e:
                    logger.warning(f"Nu am putut seta metadata pe subscription {subscription_id}: {e}")
                active_subscriptions[int(chat_id)] = subscription_id
                add_user_flow(int(chat_id))

    elif etype == "invoice.payment_succeeded":
        # Preferăm subscription -> metadata; dacă lipsește, cădem pe customer -> metadata
        sub_id = obj.get("subscription")
        customer_id = obj.get("customer")

        chat_id = None
        if sub_id:
            chat_id = _get_chat_id_from_subscription(sub_id)
        if chat_id is None and customer_id:
            chat_id = _get_chat_id_from_customer(customer_id)

        if chat_id is not None and sub_id:
            active_subscriptions[int(chat_id)] = sub_id
            add_user_flow(int(chat_id))

    elif etype == "invoice.payment_failed":
        # Non-fonduri: kick imediat + unban + anulare abonament
        sub_id = obj.get("subscription")
        customer_id = obj.get("customer")

        chat_id = None
        if sub_id:
            chat_id = _get_chat_id_from_subscription(sub_id)
        if chat_id is None and customer_id:
            chat_id = _get_chat_id_from_customer(customer_id)

        if chat_id is not None:
            cancel_stripe_subscription_for_chat(int(chat_id))
            remove_user_from_group(int(chat_id))

    elif etype == "customer.subscription.deleted":
        # Se declanșează inclusiv când noi anulăm; scoatem din grup și curățăm cache-ul
        meta = obj.get("metadata") or {}
        chat_id = meta.get("telegram_chat_id")
        if not chat_id and obj.get("customer"):
            # fallback: dacă Stripe nu a returnat metadata pe obj, încercăm din customer
            chat_id = _get_chat_id_from_customer(obj["customer"])
        if chat_id:
            remove_user_from_group(int(chat_id))
            active_subscriptions.pop(int(chat_id), None)

    return "ok", 200

@app.route("/health")
def health():
    return "ok", 200

# ---------------- Telegram ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    # Creăm sesiune de checkout pentru UTILIZATOR (chat_id în metadata)
    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        line_items=[{"price": PRICE_ID, "quantity": 1}],
        success_url="https://t.me/EscorteRO1_bot",
        cancel_url="https://t.me/EscorteRO1_bot",
        metadata={"telegram_chat_id": str(chat_id)},
        subscription_data={"metadata": {"telegram_chat_id": str(chat_id)}},
        # opțional: forțează creare customer nou, util în unele org-uri
        # customer_creation="always",
    )
    msg = (
        "Bună,\n\n"
        "⭐ Aici veți găsi conținut premium și leaks, postat de mai multe modele din România și nu numai.\n"
        "⭐ Pentru a intra în grup, trebuie să vă abonați. Un abonament costă 25 RON pentru 30 de zile.\n"
        "⭐ Pentru a vă abona, faceți clic pe butonul de mai jos.\n"
        "⭐ Vă mulțumim că ați ales să fiți membru al grupului nostru!"
    )
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("💳 Plătește abonamentul lunar", url=session.url)]]
    )
    await update.message.reply_text(msg, reply_markup=kb)

async def on_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Anulează abonamentul dacă utilizatorul părăsește grupul."""
    u: ChatMemberUpdated = update.chat_member
    if u.chat.id != GROUP_CHAT_ID:
        return

    old = u.old_chat_member.status
    new = u.new_chat_member.status

    # Identificăm CORECT utilizatorul afectat (nu pe cel care a produs evenimentul)
    affected_user_id = u.new_chat_member.user.id

    if old in ("member", "administrator") and new in ("left", "kicked"):
        logger.info(f"User {affected_user_id} a părăsit/kick grupul -> anulare abonament")
        cancel_stripe_subscription_for_chat(affected_user_id)
        remove_user_from_group(affected_user_id)

def run_flask():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(ChatMemberHandler(on_chat_member, ChatMemberHandler.CHAT_MEMBER))
    application.add_handler(ChatMemberHandler(on_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    application.run_polling(drop_pending_updates=True)
