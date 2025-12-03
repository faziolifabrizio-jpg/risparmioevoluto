import requests
from bs4 import BeautifulSoup
import time
import os

TG_TOKEN = os.environ["TG_TOKEN"]
TG_CHAT = os.environ["TG_CHAT"]   # canale @nome
AFF_TAG = os.environ["AFF_TAG"]   # es. tuo-tag-21

URL = "https://www.amazon.it/gp/goldbox"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "it-IT,it;q=0.9"
}

def send_telegram(photo_url, text):
    requests.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
        data={"chat_id": TG_CHAT, "caption": text, "parse_mode": "HTML"},
        files={"photo": requests.get(photo_url).content}
    )

def extract_deals():
    r = requests.get(URL, headers=HEADERS)
    soup = BeautifulSoup(r.text, "html.parser")

    products = []

    for block in soup.select("div.a-section.a-spacing-none.gbh1-deal"):
        title = block.select_one("span.gbDealTitle")
        price = block.select_one("span.gbDealPrice")
        link = block.select_one("a")
        img = block.select_one("img")

        if not (title and price and link and img):
            continue

        url = "https://www.amazon.it" + link["href"]
        asin = url.split("/dp/")[1][:10] if "/dp/" in url else None
        if asin:
            url = f"https://www.amazon.it/dp/{asin}?tag={AFF_TAG}"

        products.append({
            "title": title.get_text(strip=True),
            "price": price.get_text(strip=True),
            "img": img["src"],
            "url": url,
        })

    return products

def main():
    deals = extract_deals()
    for d in deals[:10]:
        text = f"<b>{d['title']}</b>\n💶 {d['price']}\n👉 <a href='{d['url']}'>Vai all'offerta</a>"
        send_telegram(d["img"], text)
        time.sleep(2)

if __name__ == "__main__":
    main()
