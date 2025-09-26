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
TELEGRAM_TOKEN = "8285233635:AAFVWJFu2xfL5OCJx0Le2zMKPVfb0bCkLTg"

STRIPE_SECRET_KEY = "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"
STRIPE_WEBHOOK_SECRET = "whsec_LxOkuricKYEikXru9KjQje65g4MNapK9"

GROUP_CHAT_ID = -1002577679941
PRICE_ID = "price_1RsNMwCFUXMdgQRzVlmVTBut"

stripe.api_key = STRIPE_SECRET_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("escorte-bot")

app = Flask(__name__)

# ---------------- STATE ----------------
active_invites: dict[int, str] = {}      # ultimul link emis per user
active_subscriptions: dict[int, str] = {}  # sub-id per user

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
    """Trimite un mesaj și îl șterge automat după ttl_seconds (default: 10 minute)."""
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
        "member_limit": member_limit,
        "expire_date": expire_date,
    }
    j = tg_call("createChatInviteLink", payload)
    if j.get("ok") and "result" in j and "invite_link" in j["result"]:
        return j["result"]["invite_link"]
    return None

def tg_revoke_invite_link(invite_link: str):
    tg_call("revokeChatInviteLink", {"chat_id": GROUP_CHAT_ID, "invite_link": invite_link})

def ban_then_unban(user_id: int):
    tg_call("banChatMember", {
        "chat_id": GROUP_CHAT_ID,
        "user_id": user_id,
        "until_date": int(time.time()) + 60,
    })
    time.sleep(1.5)
    tg_call("unbanChatMember", {
        "chat_id": GROUP_CHAT_ID,
        "user_id": user_id,
        "only_if_banned": False,
    })

# ===================== Invite flow =====================
def send_dynamic_invite(user_id: int, hours_valid: int = 24):
    """Generează link unic (1 utilizare), îl salvează și îl trimite în DM ca mesaj TEMPORAR."""
    invite = tg_create_invite_link(hours_valid=hours_valid, member_limit=1)
    if not invite:
        logger.warning(f"[INVITE] Nu am putut crea link pentru user {user_id}")
        tg_send_temp(user_id, "Momentan nu pot genera linkul. Te rog încearcă din nou.", ttl_seconds=600)
        return
    active_invites[user_id] = invite

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
    """Anulează abonamentul și oprește facturarea viitoare."""
    try:
        query = f"metadata['telegram_chat_id']:'{chat_id}' AND status:'active'"
        page = stripe.Subscription.search(query=query, limit=100)
        found = False
        for sub in page.auto_paging_iter():
            try:
                stripe.Subscription.delete(sub.id, prorate=False)
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
        if chat_id:
            send_dynamic_invite(int(chat_id))

    elif etype == "invoice.payment_failed":
        chat_id = obj.get("metadata", {}).get("telegram_chat_id")
        if chat_id:
            cancel_stripe_subscription_for_chat(int(chat_id))
            last = active_invites.pop(int(chat_id), None)
            if last:
                tg_revoke_invite_link(last)
            ban_then_unban(int(chat_id))

    elif etype == "customer.subscription.deleted":
        chat_id = obj.get("metadata", {}).get("telegram_chat_id")
        if chat_id:
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
    msg = (
        "Bună,\n\n"
        "⭐ Aici veți găsi conținut premium și leaks, postat de mai multe modele din România și nu numai.\n"
        "⭐ Pentru a intra în grup, trebuie să vă abonați. Un abonament costă 25 RON pentru 30 de zile.\n"
        "⭐ Pentru a vă abona, faceți clic pe butonul de mai jos.\n"
        "⭐ Vă mulțumim că ați ales să fiți membru al grupului nostru!"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("💳 Plătește abonamentul lunar", url=session.url)]])
    await update.message.reply_text(msg, reply_markup=kb)

async def on_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Anulează abonamentul și revocă linkul când utilizatorul iese din grup"""
    u: ChatMemberUpdated = update.chat_member
    if u.chat.id != GROUP_CHAT_ID:
        return
    old_status = u.old_chat_member.status
    new_status = u.new_chat_member.status
    affected_user_id = u.old_chat_member.user.id
    if old_status in ("member", "administrator") and new_status in ("left", "kicked"):
        logger.info(f"[CHAT] User {affected_user_id} a ieșit din grup -> anulare + ban/unban + revoke")
        cancel_stripe_subscription_for_chat(affected_user_id)
        last = active_invites.pop(int(affected_user_id), None)
        if last:
            tg_revoke_invite_link(last)
        ban_then_unban(affected_user_id)

def run_flask():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(ChatMemberHandler(on_chat_member, ChatMemberHandler.CHAT_MEMBER))
    application.add_handler(ChatMemberHandler(on_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    application.run_polling(drop_pending_updates=True)
