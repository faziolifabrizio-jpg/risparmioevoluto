import os
import asyncio
from playwright.async_api import async_playwright
import json
import time
import random
import requests

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
AFFILIATE_TAG = "risparmioevol-21"

SEARCH_URLS = [
    "https://www.amazon.it/s?k=offerte",
    "https://www.amazon.it/s?k=offerte+oggi",
    "https://www.amazon.it/s?k=sconto",
    "https://www.amazon.it/s?k=super+offerta",
]

def send_telegram_text(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[ERRORE] TOKEN mancanti")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML"
    })

def send_telegram_photo(img, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "photo": img,
        "caption": caption,
        "parse_mode": "HTML"
    })

async def scrape_amazon():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for url in SEARCH_URLS:
            print(f"[SCRAPE] Caricamento: {url}")
            await page.goto(url, wait_until="networkidle")

            await asyncio.sleep(2)  # extra load

            products = await page.query_selector_all("div.s-result-item[data-asin]")

            results = []

            for p_el in products:
                asin = await p_el.get_attribute("data-asin")
                if not asin:
                    continue

                title_el = await p_el.query_selector("h2 a span")
                img_el = await p_el.query_selector("img.s-image")
                price_el = await p_el.query_selector("span.a-price span.a-offscreen")

                if not title_el or not img_el:
                    continue

                title = await title_el.inner_text()
                img = await img_el.get_attribute("src")
                price = await price_el.inner_text() if price_el else "N/A"

                link = f"https://www.amazon.it/dp/{asin}/?tag={AFFILIATE_TAG}"

                results.append({
                    "title": title,
                    "img": img,
                    "price": price,
                    "link": link
                })

            if results:
                await browser.close()
                return results[:10]

        await browser.close()
        return []

async def main():
    print("[START] Avvio bot Amazon con Playwright...")
    send_telegram_text("🔍 <b>Cerco offerte Amazon…</b>")

    products = await scrape_amazon()

    if not products:
        send_telegram_text("❌ <b>Nessuna offerta trovata.</b>")
        return

    for p in products:
        caption = (
            f"🔥 <b>{p['title']}</b>\n"
            f"💶 Prezzo: <b>{p['price']}</b>\n\n"
            f"🔗 <a href='{p['link']}'>Apri l'offerta</a>"
        )

        send_telegram_photo(p["img"], caption)

    send_telegram_text("✅ <b>Offerte inviate.</b>")

if __name__ == "__main__":
    asyncio.run(main())
