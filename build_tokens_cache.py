# build_tokens_cache.py
# Downloads Angel One OpenAPI Scrip Master and builds a tradingsymbol -> symboltoken map

import os, json, csv, io
import requests

DATA_DIR = os.path.join("data")
os.makedirs(DATA_DIR, exist_ok=True)

# Known public endpoints from Angel One for OpenAPI Scrip Master
URLS = [
    # JSON (preferred)
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json",
    # CSV fallbacks
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.csv",
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster_2020.csv",
]

RAW_JSON_PATH = os.path.join(DATA_DIR, "OpenAPIScripMaster.json")
RAW_CSV_PATH  = os.path.join(DATA_DIR, "OpenAPIScripMaster.csv")
MAP_PATH      = os.path.join(DATA_DIR, "angel_tokens_map.json")

def download(url: str) -> bytes:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.content

def save_bytes(path: str, content: bytes) -> None:
    with open(path, "wb") as f:
        f.write(content)

def build_map_from_json(raw: bytes) -> dict:
    items = json.loads(raw.decode("utf-8"))
    # expected keys: token, symbol, name, exch_seg, instrumenttype, etc.
    out = {}
    for row in items:
        sym = row.get("symbol")
        tok = row.get("token")
        exch = row.get("exch_seg")
        if not (sym and tok and exch): 
            continue
        # We primarily want NSE cash symbols like RELIANCE-EQ
        if exch.upper() == "NSE":
            out[sym] = tok
    return out

def build_map_from_csv(raw: bytes) -> dict:
    text = raw.decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    out = {}
    for row in reader:
        sym = (row.get("symbol") or "").strip()
        tok = (row.get("token") or "").strip()
        exch = (row.get("exch_seg") or "").strip()
        if sym and tok and exch.upper()=="NSE":
            out[sym] = tok
    return out

def main():
    token_map = {}
    # Try JSON first
    for url in URLS:
        try:
            print(f"Downloading: {url}")
            raw = download(url)
            if url.lower().endswith(".json"):
                save_bytes(RAW_JSON_PATH, raw)
                token_map = build_map_from_json(raw)
            else:
                save_bytes(RAW_CSV_PATH, raw)
                token_map = build_map_from_csv(raw)
            if token_map:
                break
        except Exception as e:
            print("Download/parse failed:", e)

    if not token_map:
        raise SystemExit("Could not build token map from any known URL.")

    with open(MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(token_map, f)

    print(f"Saved token map: {MAP_PATH}")
    print(f"Symbols mapped: {len(token_map):,}")

if __name__ == "__main__":
    main()
