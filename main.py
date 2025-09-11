# app.py
import os
import time
import logging
import threading
from datetime import datetime, timedelta

import requests
import stripe
from flask import Flask, request

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
TELEGRAM_TOKEN = "8285233635:AAFESFUwipzIh9-jXvOj9tbfwTyaX08vMRU"

STRIPE_SECRET_KEY = "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"
STRIPE_WEBHOOK_SECRET = "whsec_LxOkuricKYEikXru9KjQje65g4MNapK9"

GROUP_CHAT_ID = -1002577679941
PRICE_ID = "price_1RsNMwCFUXMdgQRzVlmVTBut"

stripe.api_key = STRIPE_SECRET_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("escorte-bot")

app = Flask(__name__)

# mapăm ultimul link emis per user, pentru a-l revoca la ieșire/neplată
active_invites: dict[int, str] = {}
active_subscriptions: dict[int, str] = {}

# ===================== Telegram helpers =====================
def tg_call(method: str, payload: dict):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"
    r = requests.post(url, json=payload, timeout=10)
    try:
        j = r.json()
    except Exception:
        logger.warning(f"[TG] Non-JSON resp for {method}: {r.text}")
        return {"ok": False, "raw": r.text}
    if not j.get("ok"):
        logger.warning(f"[TG] {method} FAIL: {j}")
    return j

def tg_send(chat_id: int, text: str, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
        "parse_mode": "HTML",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup.to_dict()
    return tg_call("sendMessage", payload)

def tg_delete_message(chat_id: int, message_id: int):
    return tg_call("deleteMessage", {"chat_id": chat_id, "message_id": message_id})

def _del_after(chat_id: int, message_id: int, ttl: int):
    try:
        time.sleep(ttl)
        tg_delete_message(chat_id, message_id)
    except Exception as e:
        logger.warning(f"[TG] delete after TTL failed for {chat_id}/{message_id}: {e}")

def tg_send_temp(chat_id: int, text: str, reply_markup=None, ttl_seconds: int = 600):
    """
    Trimite un mesaj și îl șterge automat după ttl_seconds (default: 10 minute).
    Linkurile NU apar în text — doar în butoane.
    """
    resp = tg_send(chat_id, text, reply_markup)
    if resp.get("ok") and "result" in resp and "message_id" in resp["result"]:
        mid = resp["result"]["message_id"]
        th = threading.Thread(target=_del_after, args=(chat_id, mid, ttl_seconds), daemon=True)
        th.start()
    return resp

def tg_create_invite_link(hours_valid: int = 24, member_limit: int = 1) -> str | None:
    expire_date = int((datetime.utcnow() + timedelta(hours=hours_valid)).timestamp())
    payload = {
        "chat_id": GROUP_CHAT_ID,
        "member_limit": member_limit,    # one-time
        "expire_date": expire_date,      # expiră automat
    }
    j = tg_call("createChatInviteLink", payload)
    if j.get("ok") and "result" in j and "invite_link" in j["result"]:
        return j["result"]["invite_link"]
    return None

def tg_revoke_invite_link(invite_link: str):
    tg_call("revokeChatInviteLink", {"chat_id": GROUP_CHAT_ID, "invite_link": invite_link})

def ban_then_unban(user_id: int):
    # BAN 60s (forțează „kick”)
    tg_call("banChatMember", {
        "chat_id": GROUP_CHAT_ID,
        "user_id": user_id,
        "until_date": int(time.time()) + 60,
    })
    time.sleep(1.5)  # mic delay ca să se propage ban-ul
    # UNBAN (permite re-intrarea când abonamentul devine valid)
    tg_call("unbanChatMember", {
        "chat_id": GROUP_CHAT_ID,
        "user_id": user_id,
        "only_if_banned": False,
    })

# ===================== Invite flow (link mascat în buton) =====================
def send_dynamic_invite(user_id: int, hours_valid: int = 24):
    """
    Generează link unic (1 utilizare), îl salvează și îl trimite în DM ca mesaj TEMPORAR.
    NU afișează linkul în text — doar în buton.
    """
    invite = tg_create_invite_link(hours_valid=hours_valid, member_limit=1)
    if not invite:
        logger.warning(f"[INVITE] Nu am putut crea link pentru user {user_id}")
        # mesaj scurt, fără linkuri, temporar
        tg_send_temp(user_id, "Momentan nu pot genera linkul. Te rog încearcă din nou.", ttl_seconds=600)
        return
    active_invites[user_id] = invite

    # Păstrăm exact stilul tău, fără mențiuni despre „o utilizare” sau „expiră”:
    text = (
        "Bună,\n\n"
        "⭐ Aici veți găsi conținut premium și leaks, postat de mai multe modele din România și nu numai.\n\n"
        "⭐ Abonamentul este 25 RON / 30 zile.\n\n"
        "⭐ Apasă butonul de mai jos pentru a intra în grup."
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Intră în grup", url=invite)]])
    tg_send_temp(user_id, text, kb, ttl_seconds=600)

# ===================== Stripe helpers =====================
def cancel_stripe_subscription_for_chat(chat_id: int):
    """Anulează abonamentul și oprește facturarea viitoare (imediat)."""
    try:
        query = f"metadata['telegram_chat_id']:'{chat_id}' AND status:'active'"
        page = stripe.Subscription.search(query=query, limit=100)
        found = False
        for sub in page.auto_paging_iter():
            try:
                stripe.Subscription.delete(sub.id, prorate=False)  # anulare acum
                logger.info(f"[STRIPE] Abonament {sub.id} ANULAT pentru chat {chat_id}")
                found = True
            except Exception as e:
                logger.exception(f"[STRIPE] Eroare la anulare {sub.id}: {e}")
        if not found:
            logger.info(f"[STRIPE] Niciun abonament activ găsit pentru chat {chat_id}")
        active_subscriptions.pop(chat_id, None)
        return found
    except Exception as e:
        logger.exception(f"[STRIPE] Eroare la căutare subs: {e}")
        return False

def _get_chat_id_from_subscription(subscription_id: str) -> int | None:
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
    try:
        cust = stripe.Customer.retrieve(customer_id)
        meta = (cust.get("metadata") or {})
        chat_id_str = meta.get("telegram_chat_id")
        if chat_id_str:
            return int(chat_id_str)
    except Exception as e:
        logger.warning(f"Nu pot citi metadata din customer {customer_id}: {e}")
    return None

# ===================== Stripe webhook =====================
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
        chat_id = obj.get("metadata", {}).get("telegram_chat_id")
        subscription_id = obj.get("subscription")
        customer_id = obj.get("customer")
        if chat_id:
            # asigură-te că user_id e scris pe customer + subscription
            if customer_id:
                try:
                    stripe.Customer.modify(customer_id, metadata={"telegram_chat_id": str(chat_id)})
                except Exception as e:
                    logger.warning(f"Nu am putut seta metadata pe customer {customer_id}: {e}")
            if subscription_id:
                try:
                    stripe.Subscription.modify(subscription_id, metadata={"telegram_chat_id": str(chat_id)})
                except Exception as e:
                    logger.warning(f"Nu am putut seta metadata pe subscription {subscription_id}: {e}")
                active_subscriptions[int(chat_id)] = subscription_id
            # TRIMITE LINK UNIC ca MESAJ TEMPORAR (10 min), linkul e doar în buton
            send_dynamic_invite(int(chat_id), hours_valid=24)

    elif etype == "invoice.payment_succeeded":
        sub_id = obj.get("subscription")
        customer_id = obj.get("customer")
        chat_id = None
        if sub_id:
            chat_id = _get_chat_id_from_subscription(sub_id)
        if chat_id is None and customer_id:
            chat_id = _get_chat_id_from_customer(customer_id)
        if chat_id is not None:
            if sub_id:
                active_subscriptions[int(chat_id)] = sub_id
            # Retrimite invitație (dacă are nevoie să reintre) — mesaj temporar 10 min
            send_dynamic_invite(int(chat_id), hours_valid=24)

    elif etype == "invoice.payment_failed":
        sub_id = obj.get("subscription")
        customer_id = obj.get("customer")
        chat_id = None
        if sub_id:
            chat_id = _get_chat_id_from_subscription(sub_id)
        if chat_id is None and customer_id:
            chat_id = _get_chat_id_from_customer(customer_id)
        if chat_id is not None:
            # anulează, revocă ultimul link emis, ban→unban
            cancel_stripe_subscription_for_chat(int(chat_id))
            last = active_invites.pop(int(chat_id), None)
            if last:
                tg_revoke_invite_link(last)
            ban_then_unban(int(chat_id))

    elif etype == "customer.subscription.deleted":
        meta = obj.get("metadata") or {}
        chat_id = meta.get("telegram_chat_id")
        if not chat_id and obj.get("customer"):
            chat_id = _get_chat_id_from_customer(obj["customer"])
        if chat_id:
            # revocă ultimul link, apoi ban→unban
            last = active_invites.pop(int(chat_id), None)
            if last:
                tg_revoke_invite_link(last)
            ban_then_unban(int(chat_id))
            active_subscriptions.pop(int(chat_id), None)

    return "ok", 200

@app.route("/health")
def health():
    return "ok", 200

# ===================== Telegram =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        line_items=[{"price": PRICE_ID, "quantity": 1}],
        success_url="https://t.me/EscorteRO1_bot",
        cancel_url="https://t.me/EscorteRO1_bot",
        metadata={"telegram_chat_id": str(chat_id)},
        subscription_data={"metadata": {"telegram_chat_id": str(chat_id)}},
    )
    # Textul tău de prezentare — fără alte mențiuni
    msg = (
        "Bună,\n\n"
        "⭐ Aici veți găsi conținut premium și leaks, postat de mai multe modele din România și nu numai.\n\n"
        "⭐ Pentru a intra în grup, trebuie să vă abonați. Un abonament costă 25 RON pentru 30 de zile.\n\n"
        "⭐ Pentru a vă abona, faceți clic pe butonul de mai jos.\n\n"
        "⭐ Vă mulțumim că ați ales să fiți membru al grupului nostru!"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("💳 Plătește abonamentul lunar", url=session.url)]])
    # Mesaj TEMPORAR: 10 minute (link doar în buton)
    tg_send_temp(chat_id, msg, kb, ttl_seconds=600)

async def on_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Când userul părăsește grupul: anulăm subs, revocăm ultimul lui link și facem ban→unban.
    """
    u: ChatMemberUpdated = update.chat_member
    if u.chat.id != GROUP_CHAT_ID:
        return

    old_status = u.old_chat_member.status
    new_status = u.new_chat_member.status
    affected_user_id = u.old_chat_member.user.id  # persoana care a plecat

    if old_status in ("member", "administrator") and new_status in ("left", "kicked"):
        logger.info(f"User {affected_user_id} a părăsit grupul -> cancel Stripe + revoke link + ban/unban")
        cancel_stripe_subscription_for_chat(affected_user_id)
        last = active_invites.pop(int(affected_user_id), None)
        if last:
            tg_revoke_invite_link(last)
        ban_then_unban(affected_user_id)

# ===================== Run =====================
def run_flask():
    # Render: ascultă pe portul din ENV, fără reloader
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, use_reloader=False)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(ChatMemberHandler(on_chat_member, ChatMemberHandler.CHAT_MEMBER))
    application.run_polling(drop_pending_updates=True, allowed_updates=["chat_member","message"])
