import os
import requests

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_test_message():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": "✅ Test riuscito! Il bot è collegato al canale.",
        "parse_mode": "Markdown"
    }
    resp = requests.post(url, data=data)
    print("Telegram response:", resp.status_code, resp.text)

if __name__ == "__main__":
    send_test_message()
