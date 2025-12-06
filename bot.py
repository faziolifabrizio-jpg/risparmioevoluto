import os
import time
import json
import re
import ast
from typing import List, Dict, Any, Optional

import requests

# ================== CONFIG ==================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
AFFILIATE_TAG = "risparmioevol-21"

GOLDBOX_URL = "https://www.amazon.it/gp/goldbox"
MARKETPLACE_ID = "APJ6JRA9NG5V4"  # Amazon.it :contentReference[oaicite:0]{index=0}

MAX_DEALS_FETCH = 100       # quanti deal chiediamo all’API
MAX_OFFERS_SEND = 10        # quante offerte mandare a ogni esecuzione
HISTORY_FILE = "published.json"
HISTORY_HOURS = 24          # non ripubblicare la stessa offerta nelle ultime 24h

DEBUG = os.getenv("DEBUG", "0") == "1"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
}

# ================== TELEGRAM ==================


def tg_text(msg: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TG] Variabili TELEGRAM_TOKEN / TELEGRAM_CHAT_ID mancanti")
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
        print("[TG] Variabili TELEGRAM_TOKEN / TELEGRAM_CHAT_ID mancanti (photo)")
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


# ================== UTILITY ==================


def parse_price(price: Optional[str]) -> Optional[float]:
    if not price:
        return None
    try:
        p = price.replace("€", "").replace("\u00a0", "").replace(" ", "")
        p = p.replace(".", "").replace(",", ".")
        return float(p)
    except Exception:
        return None


def rating_to_stars(rating: Optional[float]) -> Optional[str]:
    if rating is None:
        return None
    try:
        full = int(rating)
        half = (rating - full) >= 0.5
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


# ================== GOLD BOX API ==================


def extract_sorted_deal_ids(html: str) -> List[str]:
    """
    Legge dal sorgente HTML la lista "sortedDealIDs"
    che Amazon usa per costruire la pagina Goldbox.
    """
    # pattern simile al gist amazon_xmas.py :contentReference[oaicite:1]{index=1}
    m = re.search(r'"sortedDealIDs"\s*:\s*(\[[^\]]+\])', html)
    if not m:
        print("[GOLDBOX] sortedDealIDs non trovati")
        return []

    text_list = m.group(1)
    try:
        # può essere JSON puro o pseudo-lista Python
        deal_ids = ast.literal_eval(text_list)
        if isinstance(deal_ids, list):
            return [str(x) for x in deal_ids]
    except Exception:
        pass

    try:
        deal_ids = json.loads(text_list)
        if isinstance(deal_ids, list):
            return [str(x) for x in deal_ids]
    except Exception:
        pass

    print("[GOLDBOX] impossibile parsare sortedDealIDs")
    return []


def get_session_id_from_cookies(cookies: Dict[str, str]) -> str:
    """
    L’API GetDeals vuole un sessionID. In genere è il cookie "session-id".
    Se non c'è, prendiamo il primo valore giusto per non far fallire la chiamata.
    """
    if "session-id" in cookies:
        return cookies["session-id"]
    if cookies:
        # primo cookie qualsiasi, come nel gist originale
        return list(cookies.values())[0]
    return ""


def call_get_deals(session: requests.Session, deal_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Effettua le POST verso /xa/dealcontent/v2/GetDeals spezzando
    la lista di dealIDs in blocchi (es. 20 alla volta) e raccoglie
    tutti i "dealDetails".
    """
    results: List[Dict[str, Any]] = []
    cookies = session.cookies.get_dict()
    session_id = get_session_id_from_cookies(cookies)

    if not session_id:
        print("[GETDEALS] Nessun sessionID trovato nei cookie")
        return []

    # spezza in blocchi da 20
    chunk_size = 20
    for i in range(0, min(len(deal_ids), MAX_DEALS_FETCH), chunk_size):
        chunk = deal_ids[i : i + chunk_size]

        deal_targets = [{"dealID": d} for d in chunk]

        payload = {
            "requestMetadata": {
                "marketplaceID": MARKETPLACE_ID,
                "clientID": "goldbox_mobile_pc",
                "sessionID": session_id,
            },
            "dealTargets": deal_targets,
            "responseSize": "ALL",
            "itemResponseSize": "DEFAULT_WITH_PREEMPTIVE_LEAKING",
        }

        nocache = str(int(time.time() * 1000))
        url = f"https://www.amazon.it/xa/dealcontent/v2/GetDeals?nocache={nocache}"

        try:
            r = session.post(
                url,
                json=payload,
                headers={"Accept": "application/json, text/javascript, */*; q=0.01"},
                timeout=20,
            )
            print("[GETDEALS] status", r.status_code, "per blocco", i // chunk_size + 1)
            if r.status_code != 200:
                continue

            data = r.json()
            deal_details = data.get("dealDetails", {})
            for d in deal_details.values():
                results.append(d)

            time.sleep(0.5)  # piccola pausa per non insospettire Amazon

        except Exception as e:
            print("[GETDEALS] Errore POST:", e)

    # debug: mostra un esempio completo di JSON di una singola offerta
    if DEBUG and results:
        print("========== ESEMPIO DEAL RAW ==========")
        print(json.dumps(results[0], indent=2, ensure_ascii=False))
        print("======================================")

    print(f"[GETDEALS] Deal totali raccolti: {len(results)}")
    return results


def fetch_goldbox_deals() -> List[Dict[str, Any]]:
    """
    - Apre la Goldbox con requests
    - Estrae sortedDealIDs
    - Chiama l’API GetDeals
    - Restituisce la lista di deal raw (JSON)
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    print("[GOLDBOX] GET pagina Goldbox…")
    try:
        r = session.get(GOLDBOX_URL, timeout=25)
    except Exception as e:
        print("[GOLDBOX] Errore HTTP:", e)
        return []

    print("[GOLDBOX] status", r.status_code)
    if r.status_code != 200:
        return []

    deal_ids = extract_sorted_deal_ids(r.text)
    if not deal_ids:
        return []

    print(f"[GOLDBOX] sortedDealIDs trovati: {len(deal_ids)}")
    return call_get_deals(session, deal_ids)


# ================== MAPPATURA DEAL → PRODOTTO ==================


def map_deal_to_product(deal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Qui traduciamo la struttura JSON di Amazon (dealDetails)
    in un dizionario semplice con:
      - asin
      - title
      - price_now_str
      - list_price_str
      - discount_pct
      - rating
      - review_count
      - image
      - url_affiliato

    ATTENZIONE:
    Amazon può cambiare le chiavi. Ho messo delle ipotesi comuni,
    e in DEBUG il bot ti stampa il JSON raw per poterle affinare.
    """
    # candidate chiavi possibili per titolo
    title = (
        deal.get("title")
        or deal.get("dealTitle")
        or deal.get("headline")
        or deal.get("primaryItem", {}).get("title")
    )

    # ASIN (potrebbe stare sotto vari campi, dipende dalla struttura)
    asin = (
        deal.get("asin")
        or deal.get("entityId")
        or deal.get("primaryItem", {}).get("asin")
    )

    # rating medio (spesso in 0-5)
    rating = None
    # esempi di percorsi possibili (lasciati “best effort”):
    rating = (
        deal.get("averageRating")
        or deal.get("rating")
        or deal.get("primaryItem", {}).get("averageRating")
    )

    if isinstance(rating, dict):
        # alcuni JSON mettono {"value":4.6, ...}
        rating = rating.get("value")

    rating_num = None
    try:
        if rating is not None:
            rating_num = float(str(rating).replace(",", "."))
    except Exception:
        rating_num = None

    # numero recensioni (stesso discorso, chiavi ipotetiche)
    review_count = (
        deal.get("totalReviews")
        or deal.get("reviewCount")
        or deal.get("primaryItem", {}).get("totalReviews")
    )

    # immagine
    image = (
        deal.get("primaryItem", {}).get("imageUrl")
        or deal.get("imageUrl")
    )

    # prezzi: ipotesi di chiavi comuni
    # (da affinare dopo aver visto il JSON reale in DEBUG)
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
        # niente sconto reale → scartiamo
        return None

    discount_pct = round((p_list - p_now) / p_list * 100)

    if not asin:
        # senza ASIN non possiamo fare link affiliato
        return None

    url_aff = f"https://www.amazon.it/dp/{asin}/?tag={AFFILIATE_TAG}"

    prod = {
        "asin": asin,
        "title": title or f"Offerta {asin}",
        "price_now_str": price_now_str or f"{p_now:.2f}€",
        "list_price_str": list_price_str or f"{p_list:.2f}€",
        "discount_pct": discount_pct,
        "rating_num": rating_num,
        "rating_stars": rating_to_stars(rating_num) if rating_num else None,
        "review_count": review_count,
        "image": image,
        "url": url_aff,
    }

    return prod


# ================== MAIN LOGIC ==================


def main():
    print("[MAIN] Avvio bot Goldbox JSON…")
    tg_text("🔍 <b>Analizzo le offerte Amazon (Goldbox API)…</b>")

    raw_deals = fetch_goldbox_deals()
    if not raw_deals:
        tg_text("❌ <b>Nessun deal ricevuto da Amazon (Goldbox API).</b>")
        return

    # mappiamo e filtriamo solo quelli con sconto valido
    products: List[Dict[str, Any]] = []
    for d in raw_deals:
        prod = map_deal_to_product(d)
        if prod:
            products.append(prod)

    if DEBUG:
        print(f"[MAIN] prodotti mappati (scontati): {len(products)}")

    if not products:
        tg_text("❌ <b>Nessun prodotto scontato trovato dalla Goldbox API.</b>")
        return

    # ordina per sconto decrescente
    products.sort(key=lambda x: x["discount_pct"], reverse=True)

    # gestisci storico
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
        caption_lines = [
            f"🔥 <b>{p['title']}</b>",
        ]
        if p.get("rating_stars"):
            caption_lines.append(f"⭐ {p['rating_stars']}")
        if p.get("review_count"):
            caption_lines.append(f"💬 {p['review_count']} recensioni")

        caption_lines.append(f"💶 Prezzo: <b>{p['price_now_str']}</b>")
        caption_lines.append(f"❌ Prezzo consigliato: <s>{p['list_price_str']}</s>")
        caption_lines.append(f"🎯 Sconto: <b>-{p['discount_pct']}%</b>")
        caption_lines.append("")
        caption_lines.append(f"🔗 <a href='{p['url']}'>Apri l'offerta</a>")

        caption = "\n".join(caption_lines)

        if p.get("image"):
            tg_photo(p["image"], caption)
        else:
            tg_text(caption)

    tg_text(f"✅ <b>Pubblicate {len(to_send)} offerte via Goldbox API.</b>")


if __name__ == "__main__":
    main()
