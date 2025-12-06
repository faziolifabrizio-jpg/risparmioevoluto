import asyncio
import json
import os
import time
from pathlib import Path
import requests
from playwright.async_api import async_playwright

# =========================
#   CONFIG
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
AFF_TAG = "risparmioevol-21"

# Memorizza ASIN pubblicati nelle ultime 24 ore
HISTORY_FILE = Path("published.json")
if not HISTORY_FILE.exists():
    HISTORY_FILE.write_text(json.dumps({}))


def load_history():
    try:
        data = json.loads(HISTORY_FILE.read_text())
        cutoff = time.time() - 86400
        return {asin: ts for asin, ts in data.items() if ts > cutoff}
    except:
        return {}


def save_history(history):
    HISTORY_FILE.write_text(json.dumps(history))


# =========================
#   TELEGRAM
# =========================
def tg_send_text(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML"
    })
    print("[TG TEXT]", r.status_code)


def tg_send_photo(photo_url, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    r = requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML"
    })
    print("[TG PHOTO]", r.status_code)


# ===============================
#   ENTRA NELLA PAGINA PRODOTTO
# ===============================
async def get_full_product_data(asin, context):
    url = f"https://www.amazon.it/dp/{asin}"
    page = await context.new_page()

    try:
        await page.goto(url, timeout=30000)

        # Cookie Amazon
        try:
            if await page.locator("#sp-cc-accept").is_visible():
                await page.locator("#sp-cc-accept").click()
        except:
            pass

        # 🔥 TITOLO (vero)
        try:
            await page.wait_for_selector("span#productTitle", timeout=8000)
            title = await page.locator("span#productTitle").inner_text()
            title = title.strip()
        except:
            title = f"Prodotto {asin}"

        # 💶 PREZZO ATTUALE
        try:
            price_now = (
                await page.locator("span.a-price span.a-offscreen").first.inner_text()
            ).strip()
        except:
            price_now = None

        # 💶 PREZZO CONSIGLIATO — versione intelligente
        price_list = None

        candidates = await page.locator(
            "span.a-price.a-text-price > span.a-offscreen, "
            "span.a-size-small.a-color-secondary.a-text-strike"
        ).all_inner_texts()

        blacklist = ["/l", "/kg", "/ml", "/100", "litro", "kg", "ml", "al "]

        for raw in candidates:
            p = raw.strip()

            if any(x in p.lower() for x in blacklist):
                continue

            try:
                val = float(p.replace("€", "").replace(",", "."))
                if price_now:
                    now_val = float(price_now.replace("€", "").replace(",", "."))
                    if val > now_val:
                        price_list = p
                        break
            except:
                pass

        # 🎯 Sconto
        discount = None
        try:
            if price_list and price_now:
                p_now = float(price_now.replace("€", "").replace(",", "."))
                p_list = float(price_list.replace("€", "").replace(",", "."))
                discount = int(((p_list - p_now) / p_list) * 100)
        except:
            pass

        return {
            "title": title,
            "price_now": price_now,
            "price_list": price_list,
            "discount": discount,
            "url": url
        }

    finally:
        await page.close()


# =========================
# PARSING CARD AMAZON
# =========================
async def parse_card(card, page):
    asin = await card.get_attribute("data-asin")
    if not asin:
        return None

    # Titolo iniziale dalla card
    try:
        raw_title = await card.locator(
            "h2, span.a-size-base-plus, span.a-size-medium"
        ).first.inner_text(timeout=1500)
        raw_title = raw_title.strip()
    except:
        raw_title = ""

    bad_words = ["pack", "kg", "ml", "pez", "litro", "variante", "conf", "%"]
    if len(raw_title) < 20 or any(w in raw_title.lower() for w in bad_words):
        raw_title = None

    # Prezzo card
    price_now = None
    try:
        el = await card.query_selector("span.a-price > span.a-offscreen")
        if el:
            price_now = (await el.inner_text()).strip()
    except:
        pass

    price_list = None
    try:
        el2 = await card.query_selector("span.a-text-price > span.a-offscreen")
        if el2:
            p = (await el2.inner_text()).strip()
            bad = ["/l", "/kg", "/ml", "/100", "litro", "kg", "ml"]
            if not any(x in p.lower() for x in bad):
                price_list = p
    except:
        pass

    # Se qualcosa manca → entriamo nella pagina
    if raw_title is None or price_list is None:
        details = await get_full_product_data(asin, page.context)
        raw_title = details["title"]
        price_now = details["price_now"]
        price_list = details["price_list"]
        discount = details["discount"]
    else:
        # sconto rapido
        discount = None
        try:
            if price_now and price_list:
                p_now = float(price_now.replace("€", "").replace(",", "."))
                p_list = float(price_list.replace("€", "").replace(",", "."))
                discount = int(((p_list - p_now) / price_list) * 100)
        except:
            pass

    # Se ancora non c’è sconto → scarta
    if not discount or discount < 10:
        return None

    return {
        "asin": asin,
        "title": raw_title,
        "price_now": price_now,
        "price_list": price_list,
        "discount": discount,
        "img": f"https://m.media-amazon.com/images/I/{asin}.jpg",
        "url": f"https://www.amazon.it/dp/{asin}/?tag={AFF_TAG}"
    }


# =========================
# SCRAPING AMAZON
# =========================

SEARCH_PAGES = [
    "https://www.amazon.it/s?k=offerte",
    "https://www.amazon.it/s?k=offerte+oggi",
    "https://www.amazon.it/s?k=sconto"
]


async def scrape_all(page):
    results = {}

    for url in SEARCH_PAGES:
        print("[SCRAPE] Carico:", url)
        await page.goto(url, timeout=30000)

        try:
            if await page.locator("#sp-cc-accept").is_visible():
                await page.locator("#sp-cc-accept").click()
                print("[COOKIE] Accettato")
        except:
            pass

        cards = await page.locator("div[data-asin]").element_handles()
        print("[SCRAPE] Carte trovate:", len(cards))

        for c in cards:
            data = await parse_card(c, page)
            if data:
                results[data["asin"]] = data

    print("[SCRAPE] Totale prodotti scontati:", len(results))
    return list(results.values())


# =========================
# MAIN BOT
# =========================
async def main():
    tg_send_text("🔍 Cerco le migliori offerte Amazon…")

    history = load_history()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(locale="it-IT")
        page = await context.new_page()

        items = await scrape_all(page)

        # rimuovi duplicati 24h
        items = [x for x in items if x["asin"] not in history]

        if not items:
            tg_send_text("❌ Nessuna nuova offerta trovata.")
            return

        # ordina per sconto
        items.sort(key=lambda x: x["discount"], reverse=True)

        publish = items[:10]

        for p in publish:
            caption = f"""🔥 <b>{p['title']}</b>

💶 <b>{p['price_now']}</b>
❌ <s>{p['price_list']}</s>
🎯 Sconto: <b>{p['discount']}%</b>

🔗 <a href="{p['url']}">Apri l'offerta</a>
"""
            tg_send_photo(p["img"], caption)
            history[p["asin"]] = time.time()
            save_history(history)

        tg_send_text("✅ Pubblicate 10 offerte migliori.")


if __name__ == "__main__":
    asyncio.run(main())
