import os
import re
import time
import requests
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

URL = "https://www.amazon.it/gp/goldbox"

def send_telegram_photo(photo_url, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "photo": photo_url, "parse_mode": "Markdown"}
    resp = requests.post(url, data=data, timeout=15)
    print("Telegram photo response:", resp.status_code, resp.text)

def send_telegram_text(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    resp = requests.post(url, data=data, timeout=15)
    print("Telegram text response:", resp.status_code, resp.text)

def fetch_html():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.amazon.it/",
        "Connection": "keep-alive",
    }
    for attempt in range(2):
        try:
            r = requests.get(URL, headers=headers, timeout=20)
            print("Amazon status:", r.status_code, "URL:", r.url)
            if r.status_code == 200:
                return r.text
        except requests.RequestException as e:
            print("Errore rete:", e)
        time.sleep(1)
    return ""

def extract():
    html = fetch_html()
    if not html:
        print("HTML vuoto o non valido.")
        return []

    # Anteprima HTML per capire se è pagina di blocco/verifica
    preview = html[:2000].replace("\n", " ")
    print("HTML preview:", preview[:1000])

    # Rilevazione “anti-bot” / verifica
    block_signals = ["Robot Check", "non sei un robot", "Inserisci i caratteri", "Enter the characters you see",
                     "Per favore verifica di essere umano", "/errors/validateCaptcha", "Sorry, we just need to make sure"]
    if any(sig.lower() in preview.lower() for sig in block_signals):
        print("Pagina di verifica/captcha rilevata.")
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []

    # Card delle offerte (regex per classi dinamiche DealGridItem)
    deal_items = soup.find_all("div", class_=re.compile(r"^DealGridItem-module__dealItem_"))
    print("DealGridItem trovati:", len(deal_items))

    def parse_node(node):
        title_node = (node.select_one("span.a-text-normal")
                      or node.select_one("a.a-link-normal[aria-label]")
                      or node.select_one("a.a-link-normal .a-text-normal"))
        if title_node and title_node.has_attr("aria-label"):
            title = title_node.get("aria-label")
        else:
            title = title_node.get_text(strip=True) if title_node else "N/A"

        img_node = node.select_one("img.s-image") or node.select_one("img")
        img = img_node.get("src") if img_node else None

        price_node = node.select_one("span.a-price span.a-offscreen") or node.select_one("span.a-offscreen")
        price = price_node.get_text(strip=True) if price_node else "N/A"

        old_price_node = node.select_one("span.a-text-price span.a-offscreen")
        old_price = old_price_node.get_text(strip=True) if old_price_node else "N/A"

        reviews_node = node.select_one("span.a-size-base") or node.select_one("span.a-size-small")
        reviews = reviews_node.get_text(strip=True) if reviews_node else "N/A"

        return {"title": title, "img": img, "price": price, "old_price": old_price, "reviews": reviews}

    for node in deal_items[:12]:
        results.append(parse_node(node))

    # Fallback: cerca blocchi prezzo/immagine nel DOM se non trovi card
    if not results:
        print("Fallback parsing attivato.")
        price_blocks = soup.select("span.a-price")
        print("Blocchi prezzo trovati:", len(price_blocks))
        for pb in price_blocks[:20]:
            container = (pb.find_parent(["div", "li", "a"], class_=True)
                         or pb.find_parent(["div", "li", "a"]))
            parsed = parse_node(container or pb)
            if parsed["title"] != "N/A" or parsed["img"]:
                results.append(parsed)

    # Deduplica
    unique = []
    seen = set()
    for r in results:
        key = (r["title"], r["price"])
        if r["title"] != "N/A" and key not in seen:
            seen.add(key)
            unique.append(r)

    print("Totale risultati estratti:", len(unique))
    return unique[:5]

def main():
    products = extract()
    if not products:
        print("Nessun prodotto trovato.")
        send_telegram_text("⚠️ Nessun prodotto trovato su Amazon GoldBox. Possibile layout dinamico o blocco anti-bot. Riproviamo al prossimo slot.")
        return

    for p in products:
        if not p["img"]:
            print("Prodotto senza immagine:", p["title"])
            continue
        caption = f"""🔥 *OFFERTA AMAZON*

📌 *{p['title']}*

💶 Prezzo: {p['price']}
❌ Prezzo consigliato: {p['old_price']}
⭐ Recensioni: {p['reviews']}

🔗 https://www.amazon.it/gp/goldbox
"""
        print("Invio prodotto:", p["title"])
        send_telegram_photo(p["img"], caption)

if __name__ == "__main__":
    main()
