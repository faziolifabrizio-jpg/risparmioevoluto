import os
import re
import requests
from bs4 import BeautifulSoup
import traceback

# Variabili ambiente
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
URL = "https://www.amazon.it/gp/goldbox"
DEBUG = os.getenv("DEBUG", "0") == "1"

# Funzioni Telegram
def send_telegram_text(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    resp = requests.post(url, data=data)
    print("Telegram text response:", resp.status_code, resp.text, flush=True)

def send_telegram_photo(photo_url, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "photo": photo_url, "parse_mode": "Markdown"}
    resp = requests.post(url, data=data)
    print("Telegram photo response:", resp.status_code, resp.text, flush=True)

# Scraping Amazon
def fetch_html():
    print("Entrato in fetch_html, DEBUG:", DEBUG, flush=True)
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(URL, headers=headers, timeout=20)
    except Exception as e:
        print("Errore durante la richiesta:", e, flush=True)
        return ""

    print("Amazon status:", r.status_code, flush=True)

    if DEBUG:
        print("=== HTML DEBUG START ===", flush=True)
        print(r.text[:2000], flush=True)  # primi 2000 caratteri
        print("=== HTML DEBUG END ===", flush=True)

    return r.text if r.status_code == 200 else ""

def extract():
    print("Entrato in extract()", flush=True)
    html = fetch_html()
    if not html:
        print("Nessun HTML ricevuto", flush=True)
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []

    # Card prodotto
    deal_items = soup.find_all("div", class_=re.compile(r"^DealGridItem-module__dealItem_"))
    print("DealGridItem trovati:", len(deal_items), flush=True)

    def parse_node(node):
        # Titolo
        title_node = node.select_one("span.a-text-normal") or node.select_one("a.a-link-normal[aria-label]")
        if title_node and title_node.has_attr("aria-label"):
            title = title_node.get("aria-label")
        else:
            title = title_node.get_text(strip=True) if title_node else "N/A"

        # Immagine
        img_node = node.select_one("img.s-image") or node.select_one("img")
        img = img_node.get("src") if img_node else None

        # Prezzo
        price_node = node.select_one("span.a-price span.a-offscreen") or node.select_one("span.a-offscreen")
        price = price_node.get_text(strip=True) if price_node else "N/A"

        # Prezzo originale
        old_price_node = node.select_one("span.a-text-price span.a-offscreen")
        old_price = old_price_node.get_text(strip=True) if old_price_node else "N/A"

        # Recensioni
        reviews_node = node.select_one("span.a-size-base") or node.select_one("span.a-size-small")
        reviews = reviews_node.get_text(strip=True) if reviews_node else "N/A"

        return {"title": title, "img": img, "price": price, "old_price": old_price, "reviews": reviews}

    for node in deal_items[:8]:
        results.append(parse_node(node))

    # Fallback se non trova card
    if not results:
        print("Fallback parsing attivato.", flush=True)
        for img in soup.select("img.s-image")[:5]:
            title = img.get("alt", "N/A")
            results.append({"title": title, "img": img.get("src"), "price": "N/A", "old_price": "N/A", "reviews": "N/A"})

    print("Totale risultati estratti:", len(results), flush=True)
    return results[:5]

def main():
    print("Entrato in main(), DEBUG mode attivo:", DEBUG, flush=True)
    products = extract()
    print("Prodotti estratti:", len(products), flush=True)

    if not products:
        send_telegram_text("⚠️ Nessun prodotto trovato su Amazon GoldBox. Il bot è attivo ma non ha trovato offerte.")
        return

    for p in products:
        if not p["img"]:
            continue
        caption = f"""🔥 *OFFERTA AMAZON*

📌 *{p['title']}*

💶 Prezzo: {p['price']}
❌ Prezzo consigliato: {p['old_price']}
⭐ Recensioni: {p['reviews']}

🔗 https://www.amazon.it/gp/goldbox
"""
        send_telegram_photo(p["img"], caption)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Errore in main:", e, flush=True)
        traceback.print_exc()
