import os
import asyncio
import json
import time
from typing import List, Dict, Any, Optional

import requests
from playwright.async_api import async_playwright, Page

# ========= CONFIG =========

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
AFFILIATE_TAG = "risparmioevol-21"

SEARCH_URLS = [
    "https://www.amazon.it/s?k=offerte",
    "https://www.amazon.it/s?k=offerte+oggi",
    "https://www.amazon.it/s?k=sconto",
]

MAX_OFFERS_SEND = 10
HISTORY_FILE = "published.json"
HISTORY_HOURS = 24

LOCAL_TEST = os.getenv("LOCAL_TEST", "0") == "1"  # 1 = vedi il browser, 0 = headless

# ========= TELEGRAM =========


def tg_text(msg: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TG] Variabili Telegram mancanti, salto testo")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(url, data=data, timeout=20)
        print("[TG text]", r.status_code)
    except Exception as e:
        print("[TG text ERRORE]", e)


def tg_photo(photo_url: str, caption: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TG] Variabili Telegram mancanti, salto foto")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML",
    }
    try:
        r = requests.post(url, data=data, timeout=20)
        print("[TG photo]", r.status_code)
    except Exception as e:
        print("[TG photo ERRORE]", e)


# ========= UTILITY =========


def parse_price(price: Optional[str]) -> Optional[float]:
    if not price:
        return None
    try:
        p = price.replace("€", "").replace("\u00a0", "").replace(" ", "")
        p = p.replace(".", "").replace(",", ".")
        return float(p)
    except Exception:
        return None


def rating_to_stars(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    try:
        num = float(raw.split(" ")[0].replace(",", "."))
        full = int(num)
        half = num - full >= 0.5
        return "⭐" * full + ("✨" if half else "")
    except Exception:
        return None


def load_history() -> List[Dict[str, Any]]:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_history(history: List[Dict[str, Any]]) -> None:
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False)
    except Exception as e:
        print("[HISTORY] Errore salvataggio:", e)


def filter_recent(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cutoff = time.time() - HISTORY_HOURS * 3600
    return [h for h in history if h.get("ts", 0) >= cutoff]


# ========= PLAYWRIGHT HELPERS =========


async def accept_cookies(page: Page) -> None:
    selectors = [
        "#sp-cc-accept",
        "button#sp-cc-accept",
        "input#sp-cc-accept",
        "button:has-text('Accetta')",
        "button:has-text('Accetta tutto')",
    ]
    for sel in selectors:
        try:
            btn = await page.query_selector(sel)
            if btn:
                print(f"[COOKIES] Click su {sel}")
                await btn.click()
                await asyncio.sleep(1.5)
                return
        except Exception:
            continue
    print("[COOKIES] Nessun popup cookie trovato (forse già accettato).")


async def scrape_search_page(page: Page, url: str) -> List[Dict[str, Any]]:
    print(f"[SCRAPE] Carico pagina: {url}")
    await page.goto(url, wait_until="domcontentloaded")
    await asyncio.sleep(2)
    await accept_cookies(page)
    await asyncio.sleep(2)

    # scroll per caricare più risultati
    for i in range(5):
        await page.mouse.wheel(0, 3000)
        await asyncio.sleep(1.5)

    cards = await page.query_selector_all(
        "div.s-main-slot div[data-component-type='s-search-result'][data-asin]"
    )
    print(f"[SCRAPE] Carte trovate su questa pagina: {len(cards)}")

    products: List[Dict[str, Any]] = []

    for c in cards:
        try:
            asin = await c.get_attribute("data-asin")
            if not asin:
                continue

            # titolo
            title_el = await c.query_selector("h2 a span")
            title = (await title_el.inner_text()).strip() if title_el else None

            # prezzo attuale
            price_now_el = await c.query_selector("span.a-price span.a-offscreen")
            price_now_str = (await price_now_el.inner_text()).strip() if price_now_el else None

            # prezzo barrato / consigliato
            list_price_el = await c.query_selector("span.a-text-price span.a-offscreen")
            list_price_str = (await list_price_el.inner_text()).strip() if list_price_el else None

            # rating
            rating_el = await c.query_selector("span.a-icon-alt")
            rating_str = (await rating_el.inner_text()).strip() if rating_el else None

            # recensioni
            reviews_el = await c.query_selector("span[aria-label$='valutazioni'], span[aria-label$='valutazione'], span.a-size-base.s-underline-text")
            reviews_str = (await reviews_el.inner_text()).strip() if reviews_el else None

            # immagine
            img_el = await c.query_selector("img.s-image")
            img_url = await img_el.get_attribute("src") if img_el else None

            p_now = parse_price(price_now_str)
            p_list = parse_price(list_price_str)

            if not p_now or not p_list or p_now >= p_list:
                # niente sconto vero su questa card
                continue

            discount_pct = round((p_list - p_now) / p_list * 100)
            stars = rating_to_stars(rating_str) if rating_str else None

            url_aff = f"https://www.amazon.it/dp/{asin}/?tag={AFFILIATE_TAG}"

            products.append(
                {
                    "asin": asin,
                    "title": title or f"Prodotto {asin}",
                    "price_now_str": price_now_str or f"{p_now:.2f}€",
                    "list_price_str": list_price_str or f"{p_list:.2f}€",
                    "discount_pct": discount_pct,
                    "rating_raw": rating_str,
                    "rating_stars": stars,
                    "reviews_str": reviews_str,
                    "image": img_url,
                    "url": url_aff,
                }
            )
        except Exception as e:
            print("[SCRAPE] Errore su una card:", e)
            continue

    print(f"[SCRAPE] Prodotti scontati trovati su questa pagina: {len(products)}")
    return products


async def collect_all_products() -> List[Dict[str, Any]]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not LOCAL_TEST,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        all_products: List[Dict[str, Any]] = []
        for url in SEARCH_URLS:
            prods = await scrape_search_page(page, url)
            all_products.extend(prods)

        await browser.close()

    # deduplica per ASIN
    unique: Dict[str, Dict[str, Any]] = {}
    for p in all_products:
        unique[p["asin"]] = p

    merged = list(unique.values())
    print(f"[MAIN] Prodotti scontati totali (deduplicati): {len(merged)}")
    return merged


# ========= MAIN =========


async def main_async() -> None:
    print("[MAIN] Avvio bot Amazon (Playwright + search offerte)…")
    tg_text("🔍 <b>Analizzo le offerte Amazon…</b>")

    products = await collect_all_products()
    if not products:
        tg_text("❌ <b>Nessun prodotto scontato trovato nelle pagine offerte.</b>")
        return

    # ordina per sconto
    products.sort(key=lambda x: x["discount_pct"], reverse=True)

    # history
    history = filter_recent(load_history())
    seen = {h["asin"] for h in history}
    now = time.time()

    to_send: List[Dict[str, Any]] = []
    for p in products:
        if p["asin"] in seen:
            continue
        to_send.append(p)
        history.append({"asin": p["asin"], "ts": now})
        if len(to_send) >= MAX_OFFERS_SEND:
            break

    save_history(history)

    if not to_send:
        tg_text("ℹ️ Nessuna nuova offerta (tutte già pubblicate nelle ultime 24h).")
        return

    # invio su Telegram
    for p in to_send:
        lines = [f"🔥 <b>{p['title']}</b>"]

        if p.get("rating_stars"):
            if p.get("reviews_str"):
                lines.append(f"⭐ {p['rating_stars']}  ({p['reviews_str']})")
            else:
                lines.append(f"⭐ {p['rating_stars']}")

        lines.append(f"💶 Prezzo: <b>{p['price_now_str']}</b>")
        lines.append(f"❌ Prezzo consigliato: <s>{p['list_price_str']}</s>")
        lines.append(f"🎯 Sconto: <b>-{p['discount_pct']}%</b>")
        lines.append("")
        lines.append(f"🔗 <a href='{p['url']}'>Apri l'offerta</a>")

        caption = "\n".join(lines)

        if p.get("image"):
            tg_photo(p["image"], caption)
        else:
            tg_text(caption)

    tg_text(f"✅ <b>Pubblicate {len(to_send)} offerte con lo sconto più alto.</b>")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
