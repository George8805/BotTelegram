import requests
import time

BOT_TOKEN = "7718252241:AAFujt2e083856mz3kcHtFmlkXw5aYHOm5c"

def remove_webhook():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
    response = requests.get(url)
    print("Webhook dezactivat:", response.json())

def get_updates():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    response = requests.get(url)
    return response.json()

def extract_chat_id():
    updates = get_updates()
    if "result" in updates and len(updates["result"]) > 0:
        chat = updates["result"][-1]["message"]["chat"]
        print(f"✅ Chat ID-ul tău este: {chat['id']}")
    else:
        print("❗ Trimite un mesaj botului tău în Telegram și apoi rulează din nou scriptul.")

if __name__ == "__main__":
    remove_webhook()
    time.sleep(1)
    extract_chat_id()
