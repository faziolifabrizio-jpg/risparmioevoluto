import os
import time
import json
import re
import ast
from typing import List, Dict, Any, Optional
import requests


# ======= CONFIG =======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
AFFILIATE_TAG = "risparmioevol-21"

GOLDBOX_URL = "https://www.amazon.it/gp/goldbox"
MARKETPLACE_ID = "APJ6JRA9NG5V4"  # marketplace Amazon Italia

MAX_DEALS_FETCH = 100      # quanti deal chiedere massimo
MAX_OFFERS_SEND = 10       # quante offerte pubblicare
HISTORY_FILE = "published.json"
HISTORY_HOURS = 24         # non ripostare negli ultimi 24h

# fascia oraria
START_HOUR = 8
END_HOUR = 23

DEBUG = os.getenv("DEBUG", "0") == "1"


# ======= HEADERS =======
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8",
    "Connection": "keep-alive",
}


# ======= TELEGRAM =======

def tg_text(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TG] TOKEN o CHAT_ID mancanti")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        r = requests.post(url, data=data, timeout=20)
        print("[TG text]", r.status_code)
    except Exception as e:
        print("[TG ERRORE]", e)


def tg_photo(photo_url: str, caption: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TG] TOKEN o CHAT_ID mancanti (photo)")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML"
    }
    try:
        r = requests.post(url, data=data, timeout=20)
        print("[TG photo]", r.status_code)
    except Exception as e:
        print("[TG photo ERRORE]", e)


# ======= UTILITY =======

def parse_price(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    try:
        s = s.replace("€", "").replace("\u00a0", "").replace(" ", "")
        s = s.replace(".", "").replace(",", ".")
        return float(s)
    except:
        return None


def rating_to_stars(r: Optional[float]) -> Optional[str]:
    if r is None:
        return None
    try:
        full = int(r)
        half = (r - full) >= 0.5
        return "⭐" * full + ("✨" if half else "")
    except:
        return None


def load_history() -> List[Dict[str, Any]]:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def save_history(x: List[Dict[str, Any]]):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(x, f, ensure_ascii=False)
    except Exception as e:
        print("[HISTORY] Errore salvataggio", e)


def filter_recent(hist):
    cutoff = time.time() - HISTORY_HOURS * 3600
    return [h for h in hist if h.get("ts", 0) >= cutoff]


# ======= GOLD BOX JSON API =======

def extract_deal_ids(html: str) -> List[str]:
    m = re.search(r'"sortedDealIDs"\s*:\s*(\[[^\]]+\])', html)
    if not m:
        print("[GOLDBOX] sortedDealIDs non trovati")
        return []
    text_list = m.group(1)
    try:
        ids = ast.literal_eval(text_list)
        return [str(x) for x in ids]
    except:
        pass
    try:
        ids = json.loads(text_list)
        return [str(x) for x in ids]
    except:
        pass
    print("[GOLDBOX] Errore parsing sortedDealIDs")
    return []


def get_session_cookie(session: requests.Session) -> str:
    cookies = session.cookies.get_dict()
    return cookies.get("session-id", next(iter(cookies.values()), ""))


def call_api(session: requests.Session, deal_ids: List[str]) -> List[Dict[str, Any]]:
    results = []
    session_id = get_session_cookie(session)
    if not session_id:
        print("[API] Nessun sessionID trovato")
        return []

    chunk_size = 20
    for i in range(0, min(len(deal_ids), MAX_DEALS_FETCH), chunk_size):
        chunk = deal_ids[i:i+chunk_size]

        payload = {
            "requestMetadata": {
                "marketplaceID": MARKETPLACE_ID,
                "clientID": "goldbox_mobile_pc",
                "sessionID": session_id,
            },
            "dealTargets": [{"dealID": d} for d in chunk],
            "responseSize": "ALL",
            "itemResponseSize": "DEFAULT_WITH_PREEMPTIVE_LEAKING",
        }

        url = f"https://www.amazon.it/xa/dealcontent/v2/GetDeals?nocache={int(time.time()*1000)}"

        try:
            r = session.post(url, json=payload, timeout=20)
            print("[API] status", r.status_code)
            if r.status_code != 200:
                continue

            data = r.json()
            deal_details = data.get("dealDetails", {})
            for d in deal_details.values():
                results.append(d)

        except Exception as e:
            print("[API] Errore:", e)

        time.sleep(0.5)

    print(f"[API] Deal raccolti: {len(results)}")
    return results


def fetch_goldbox_json() -> List[Dict[str, Any]]:
    s = requests.Session()
    s.headers.update(HEADERS)

    print("[GOLDBOX] GET pagina...")
    try:
        r = s.get(GOLDBOX_URL, timeout=25)
    except Exception as e:
        print("[GOLDBOX] Errore:", e)
        return []

    if r.status_code != 200:
        print("[GOLDBOX] Status:", r.status_code)
        return []

    ids = extract_deal_ids(r.text)
    if not ids:
        return []

    print("[GOLDBOX] sortedDealIDs:", len(ids))
    return call_api(s, ids)


# ======= MAP JSON → PRODOTTO =======

def map_deal(deal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title = (
        deal.get("title")
        or deal.get("dealTitle")
        or deal.get("headline")
        or deal.get("primaryItem", {}).get("title")
    )

    asin = (
        deal.get("asin")
        or deal.get("entityId")
        or deal.get("primaryItem", {}).get("asin")
    )

    if not asin:
        return None

    # prezzi
    price_now_str = (
        deal.get("dealPrice", {}).get("formattedPrice")
        or deal.get("price", {}).get("formattedPrice")
        or deal.get("displayPrice")
    )

    list_price_str = (
        deal.get("listPrice", {}).get("formattedPrice")
        or deal.get("originalPrice", {}).get("formattedPrice")
        or deal.get("wasPrice", {}).get("formattedPrice")
    )

    p_now = parse_price(price_now_str)
    p_list = parse_price(list_price_str)

    if not p_now or not p_list or p_now >= p_list:
        return None  # niente sconto

    discount_pct = round((p_list - p_now) / p_list * 100)

    rating = (
        deal.get("averageRating")
        or deal.get("rating")
        or deal.get("primaryItem", {}).get("averageRating")
    )

    if isinstance(rating, dict):
        rating = rating.get("value")

    try:
        rating_num = float(str(rating).replace(",", ".")) if rating else None
    except:
        rating_num = None

    review_count = (
        deal.get("totalReviews")
        or deal.get("reviewCount")
        or deal.get("primaryItem", {}).get("totalReviews")
    )

    image = (
        deal.get("primaryItem", {}).get("imageUrl")
        or deal.get("imageUrl")
    )

    url_aff = f"https://www.amazon.it/dp/{asin}/?tag={AFFILIATE_TAG}"

    return {
        "asin": asin,
        "title": title or f"Offerta {asin}",
        "price_now": price_now_str or f"{p_now:.2f}€",
        "price_list": list_price_str or f"{p_list:.2f}€",
        "discount_pct": discount_pct,
        "rating": rating_num,
        "stars": rating_to_stars(rating_num),
        "reviews": review_count,
        "image": image,
        "url": url_aff,
    }


# ======= MAIN =======

def main():
    # BLOCCO ORARIO
    hour = time.localtime().tm_hour
    if not (START_HOUR <= hour <= END_HOUR):
        print("[MAIN] Fuori fascia oraria")
        return

    tg_text("🔍 <b>Analizzo le offerte Amazon (Goldbox API)…</b>")

    deals = fetch_goldbox_json()
    if not deals:
        tg_text("❌ Nessun deal ricevuto da Amazon.")
        return

    products = []
    for d in deals:
        m = map_deal(d)
        if m:
            products.append(m)

    if not products:
        tg_text("❌ Nessun prodotto scontato trovato.")
        return

    products.sort(key=lambda x: x["discount_pct"], reverse=True)

    history = filter_recent(load_history())
    seen = {h["asin"] for h in history}
    now = time.time()

    to_send = []
    for p in products:
        if p["asin"] in seen:
            continue
        to_send.append(p)
        history.append({"asin": p["asin"], "ts": now})
        if len(to_send) >= MAX_OFFERS_SEND:
            break

    save_history(history)

    if not to_send:
        tg_text("ℹ️ Nessuna nuova offerta da pubblicare.")
        return

    for p in to_send:
        lines = [
            f"🔥 <b>{p['title']}</b>",
        ]
        if p["stars"]:
            lines.append(f"⭐ {p['stars']}")
        if p["reviews"]:
            lines.append(f"💬 {p['reviews']} recensioni")
        lines.append(f"💶 Prezzo: <b>{p['price_now']}</b>")
        lines.append(f"❌ Prezzo consigliato: <s>{p['price_list']}</s>")
        lines.append(f"🎯 Sconto: <b>-{p['discount_pct']}%</b>")
        lines.append("")
        lines.append(f"🔗 <a href='{p['url']}'>Apri l'offerta</a>")

        caption = "\n".join(lines)

        if p["image"]:
            tg_photo(p["image"], caption)
        else:
            tg_text(caption)

    tg_text(f"✅ Pubblicate {len(to_send)} offerte.")


if __name__ == "__main__":
    main()
