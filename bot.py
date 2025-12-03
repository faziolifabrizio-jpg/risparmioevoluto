import os
import re
import time
import requests
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

URL = "https://www.amazon.it/gp/goldbox"

def send_telegram(photo_url, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "caption": text,
        "photo": photo_url,
        "parse_mode": "Markdown"
    }
    resp = requests.post(url, data=data, timeout=15)
    print("Telegram response:", resp.status_code, resp.text)

def send_telegram_text(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    resp = requests.post(url, data=data, timeout=15)
    print("Telegram text response:", resp.status_code, resp.text)

def fetch_html():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0 Safari/537.36",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    for attempt in range(3):
        try:
            r = requests.get(URL, headers=headers, timeout=20)
            print("Amazon status:", r.status_code)
            if r.status_code == 200 and "goldbox" in r.url:
                return r.text
        except requests.RequestException as e:
            print("Errore rete:", e)
        time.sleep(2)
    return ""

def extract():
    html = fetch_html()
    if not html:
        print("HTML vuoto o non valido.")
        return []

    # Debug ridotto: primi 1000 caratteri per capire la pagina
    print("HTML head preview:", html[:500].replace("\n", " ")[:500])

    soup = BeautifulSoup(html, "html.parser")
    results = []

    # 1) Cattura card deal grid via regex su classi dinamiche
    deal_items = soup.find_all("div", class_=re.compile(r"^DealGridItem-module__dealItem_"))
    print(f"DealGridItem trovati: {len(deal_items)}")

    def parse_item(node):
        # Titolo: prova sequenza di selettori comuni
        title_node = node.select_one("span.a-text-normal") or node.select_one("a.a-link-normal[aria-label]") \
                     or node.select_one("a.a-link-normal .a-text-normal")
        title = (title_node.get("aria-label") if title_node and title_node.has_attr("aria-label")
                 else title_node.get_text(strip=True) if title_node else "N/A")

        # Immagine
        img_node = node.select_one("img.s-image") or node.select_one("img")
        img = img_node.get("src") if img_node else None

        # Prezzi
        price_node = node.select_one("span.a-price span.a-offscreen") or node.select_one("span.a-offscreen")
        price = price_node.get_text(strip=True) if price_node else "N/A"

        old_price_node = node.select_one("span.a-text-price span.a-offscreen")
        old_price = old_price_node.get_text(strip=True) if old_price_node else "N/A"

        # Recensioni (best effort)
        reviews_node = node.select_one("span.a-size-base") or node.select_one("span.a-size-small")
        reviews = reviews_node.get_text(strip=True) if reviews_node else "N/A"

        return {
            "title": title,
            "img": img,
            "price": price,
            "old_price": old_price,
            "reviews": reviews
        }

    for node in deal_items[:8]:
        results.append(parse_item(node))

    # 2) Fallback: se 0, prova blocchi con prezzo immagini generici
    if not results:
        print("Fallback parsing attivato.")
        price_blocks = soup.select("span.a-price")
        print("Blocchi prezzo trovati:", len(price_blocks))
        for pb in price_blocks[:10]:
            container = pb.find_parent(["div", "li", "a"], class_=True)
            if not container:
                container = pb.find_parent(["div", "li", "a"])
            node = container or pb

            parsed = parse_item(node)
            # Filtra solo se almeno titolo o immagine presente
            if parsed["title"] != "N/A" or parsed["img"]:
                results.append(parsed)

    # Deduplica per titolo+prezzo
    unique = []
    seen = set()
    for r in results:
        key = (r["title"], r["price"])
        if key not in seen and r["title"] != "N/A":
            seen.add(key)
            unique.append(r)

    print(f"Totale risultati estratti: {len(unique)}")
    return unique[:5]

def main():
    products = extract()
    if not products:
        print("Nessun prodotto trovato.")
        send_telegram_text("⚠️ Nessun prodotto trovato su Amazon GoldBox. Potrebbe essere cambiato il layout o attivo un blocco. Riproviamo al prossimo slot.")
        return

    for p in products:
        if not p["img"]:
            print(f"Prodotto senza immagine: {p['title']}")
            continue
        text = f"""🔥 *OFFERTA AMAZON*

📌 *{p['title']}*

💶 Prezzo: {p['price']}
❌ Prezzo consigliato: {p['old_price']}
⭐ Recensioni: {p['reviews']}

🔗 https://www.amazon.it/gp/goldbox
"""
        print("Invio prodotto:", p['title'])
        send_telegram(p["img"], text)

if __name__ == "__main__":
    main()
