import os
import requests
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
URL = "https://www.amazon.it/gp/goldbox"

def send_telegram_text(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    resp = requests.post(url, data=data)
    print("Telegram response:", resp.status_code, resp.text)

def extract():
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(URL, headers=headers)
    print("Amazon status:", r.status_code)
    soup = BeautifulSoup(r.text, "html.parser")
    items = soup.select("div.DealGridItem-module__dealItem_")
    print(f"Trovati {len(items)} items")
    return items

def main():
    items = extract()
    if not items:
        send_telegram_text("⚠️ Nessun prodotto trovato su Amazon GoldBox. Il bot è attivo ma non ha trovato offerte.")
    else:
        send_telegram_text(f"✅ Ho trovato {len(items)} offerte su Amazon GoldBox!")

if __name__ == "__main__":
    main()
