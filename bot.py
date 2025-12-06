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

MAX_CARDS_PER_PAGE = 40      
MIN_DISCOUNT = 10            
MAX_OFFERS_SEND = 10         

SEARCH_PAGES = [
    "https://www.amazon.it/s?k=offerte",
    "https://www.amazon.it/s?k=offerte+oggi",
    "https://www.amazon.it/s?k=sconto",
]

HISTORY_FILE = Path("published.json")
if not HISTORY_FILE.exists():
    HISTORY_FILE.write_text("{}")


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
def tg_send_text(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TG TEXT] Variabili non impostate")
        return
    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
        timeout=20,
    )
    print("[TG TEXT]", r.status_code)


def tg_send_photo(photo_url: str, caption: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TG PHOTO] Variabili non impostate")
        return
    if not photo_url:
        tg_send_text(caption)
        return
    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": "HTML",
        },
        timeout=20,
    )
    print("[TG PHOTO]", r.status_code, r.text)


# ===============================
#   DETTAGLIO PRODOTTO COMPLETO
# ===============================
async def get_full_product_data(asin: str, context):
    url = f"https://www.amazon.it/dp/{asin}"
    url = url.replace("&", "&amp;")

    page = await context.new_page()
    print(f"[DETAIL] Apro pagina {url}")

    title = f"Prodotto {asin}"
    price_now = None
    price_list = None
    discount = None
    img_url = None

    try:
        await page.goto(url, timeout=30000)

        try:
            if await page.locator("#sp-cc-accept").is_visible():
                await page.locator("#sp-cc-accept").click()
                print("[DETAIL COOKIE] Accettato")
        except:
            pass

        # Titolo
        try:
            await page.wait_for_selector("span#productTitle", timeout=8000)
            title = (await page.locator("span#productTitle").inner_text()).strip()
        except:
            pass

        # Immagine
        try:
            img_url = await page.locator("#imgTagWrapperId img").get_attribute("src")
        except:
            pass

        # Prezzo attuale
        try:
            price_now = (await page.locator("span.a-price span.a-offscreen").first.inner_text()).strip()
        except:
            pass

        # Prezzo consigliato filtrato (no €/L)
        try:
            all_prices = await page.locator(
                "span.a-price.a-text-price > span.a-offscreen, span.a-text-strike"
            ).all_inner_texts()

            blacklist = ["/l", "/kg", "/ml", "litro", "/100", "confezione"]
            for p in all_prices:
                p_clean = p.strip()
                if any(x in p_clean.lower() for x in blacklist):
                    continue
                try:
                    v = float(p_clean.replace("€", "").replace(",", "."))
                    if price_now:
                        now_val = float(price_now.replace("€", "").replace(",", "."))
                        if v > now_val:
                            price_list = p_clean
                            break
                except:
                    continue
        except:
            pass

        # Sconto
        try:
            if price_now and price_list:
                now = float(price_now.replace("€", "").replace(",", "."))
                lst = float(price_list.replace("€", "").replace(",", "."))
                discount = round(100 - (now / lst * 100))
        except:
            pass

    finally:
        await page.close()

    print(f"[DETAIL] FINITO ASIN {asin} → sconto: {discount}")
    return {
        "title": title,
        "price_now": price_now,
        "price_list": price_list,
        "discount": discount,
        "img": img_url,
        "url": url,
    }


# =========================
# PARSING CARD
# =========================
async def parse_card(card, page, idx, total):
    print(f"[CHECK] Card {idx}/{total}")

    asin = await card.get_attribute("data-asin")
    if not asin:
        return None

    # ▼ IMMAGINE REALE
    img_url = None
    try:
        img_el = await card.query_selector("img.s-image")
        if img_el:
            img_url = await img_el.get_attribute("src")
    except:
        pass

    # ▼ TITOLO
    title = None
    try:
        title_el = await card.query_selector("h2 span")
        if title_el:
            title = (await title_el.inner_text()).strip()
    except:
        pass

    # ▼ PREZZO ATTUALE
    price_now = None
    try:
        pn = await card.query_selector("span.a-price > span.a-offscreen")
        if pn:
            price_now = (await pn.inner_text()).strip()
    except:
        pass

    # ▼ PREZZO LISTA filtrato (no €/L)
    price_list = None
    try:
        pl = await card.query_selector("span.a-text-price > span.a-offscreen")
        if pl:
            raw = (await pl.inner_text()).strip()
            blacklist = ["/l", "/kg", "/ml", "/100", "litro"]
            if not any(x in raw.lower() for x in blacklist):
                price_list = raw
    except:
        pass

    # Calcolo sconto
    discount = None
    try:
        if price_now and price_list:
            now = float(price_now.replace("€", "").replace(",", "."))
            lst = float(price_list.replace("€", "").replace(",", "."))
            if lst > now:
                discount = round(100 - (now / lst * 100))
    except:
        pass

    # Se manca qualcosa → ENTRO NELLA PAGINA PRODOTTO
    if not title or not price_list or discount is None:
        print(f"[DETAIL] Entrando nel prodotto per ASIN {asin}")
        details = await get_full_product_data(asin, page.context)
        title = details["title"]
        price_now = details["price_now"]
        price_list = details["price_list"]
        discount = details["discount"]
        if details["img"]:
            img_url = details["img"]

    # Scarta se sconto insufficiente
    if discount is None or discount < MIN_DISCOUNT:
        print(f"[SKIP] ASIN {asin} → sconto insufficiente ({discount})")
        return None

    print(f"[OK] ASIN {asin}, sconto {discount}%")

    link = f"https://www.amazon.it/dp/{asin}/?tag={AFF_TAG}".replace("&", "&amp;")

    return {
        "asin": asin,
        "title": title,
        "price_now": price_now,
        "price_list": price_list,
        "discount": discount,
        "img": img_url,
        "url": link,
    }


# =========================
# SCRAPE TOTALE
# =========================
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
        count = len(cards)
        print(f"[SCRAPE] Carte trovate: {count}")

        cards = cards[:MAX_CARDS_PER_PAGE]

        for idx, card in enumerate(cards, start=1):
            data = await parse_card(card, page, idx, len(cards))
            if data:
                results[data["asin"]] = data

    print("[SCRAPE] Totale prodotti scontati:", len(results))
    return list(results.values())


# =========================
# MAIN
# =========================
async def main():
    tg_send_text("🔍 Cerco le migliori offerte Amazon…")

    history = load_history()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(locale="it-IT")
        page = await context.new_page()

        items = await scrape_all(page)

        # Rimuovi già pubblicati (24h)
        items = [x for x in items if x["asin"] not in history]

        if not items:
            tg_send_text("❌ Nessuna nuova offerta trovata.")
            await browser.close()
            return

        # Ordina per sconto discendente
        items.sort(key=lambda x: x["discount"], reverse=True)

        publish = items[:MAX_OFFERS_SEND]

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

        tg_send_text(f"✅ Pubblicate {len(publish)} offerte migliori (per sconto).")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
