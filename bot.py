import os
import re
import requests
from bs4 import BeautifulSoup
import sys
import traceback

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
URL = "https://www.amazon.it/gp/goldbox"

DEBUG = os.getenv("DEBUG", "0") == "1"

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
        print(r.text[:2000], flush=True)
        print("=== HTML DEBUG END ===", flush=True)

    return r.text if r.status_code == 200 else ""

def main():
    print("Entrato in main(), DEBUG mode attivo:", DEBUG, flush=True)
    html = fetch_html()
    if not html:
        print("Nessun HTML ricevuto", flush=True)
    else:
        print("HTML ricevuto, lunghezza:", len(html), flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Errore in main:", e, flush=True)
        traceback.print_exc()
