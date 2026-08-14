"""
Paso 2: Para cada store_id de Rappi Turbo, baja el catálogo de "Cervezas"
(categoría + subcategorías) y arma un CSV con qué SKUs tienen el badge
de "Frío" (attributes.cold_beer == true).

Uso:
    python scrape_beers.py                  # usa stores.json generado por discover_stores.py
    python scrape_beers.py --store-ids 266928,185472   # o pasás los store_id a mano

Salida: cervezas_frias_rappi.csv
"""
import argparse
import csv
import json
import re
import time
import random

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
}

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)

REQUEST_DELAY_RANGE = (2.0, 4.0)  # segundos entre requests, para no pegarle fuerte al sitio
MAX_RETRIES = 4


def polite_get(session, url):
    for attempt in range(1, MAX_RETRIES + 1):
        resp = session.get(url, headers=HEADERS, timeout=20)
        if resp.status_code == 200:
            time.sleep(random.uniform(*REQUEST_DELAY_RANGE))
            return resp
        if resp.status_code == 429:
            wait = 15 * attempt
            print(f"    [429] rate limited, esperando {wait}s (intento {attempt}/{MAX_RETRIES})...")
            time.sleep(wait)
            continue
        print(f"    [{resp.status_code}] error en {url}")
        time.sleep(random.uniform(*REQUEST_DELAY_RANGE))
        return resp
    return resp


def get_next_data(session, url):
    resp = polite_get(session, url)
    if resp is None or resp.status_code != 200:
        return None
    m = NEXT_DATA_RE.search(resp.text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def extract_products_from_fallback(fallback):
    """El JSON embebido puede venir de la página de categoría (sub_aisles_response)
    o de una subcategoría (aisle_detail_response). Busca productos en ambas formas."""
    products = []
    for payload in fallback.values():
        for key in ("sub_aisles_response", "aisle_detail_response"):
            resp = payload.get(key)
            if not resp:
                continue
            comps = resp.get("data", {}).get("components", [])
            for c in comps:
                resource = c.get("resource", {})
                prods = resource.get("products")
                if prods:
                    products.extend(prods)
                # headers también pueden traer categorías con productos embebidos en algunos casos
            headers = resp.get("data", {}).get("headers", [])
            for h in headers:
                resource = h.get("resource", {})
                prods = resource.get("products")
                if prods:
                    products.extend(prods)
    return products


def get_subcategories(session, store_id, base_category="cervezas"):
    """Devuelve lista de (nombre, friendly_url) de subcategorías dentro de la categoría base."""
    url = f"https://www.rappi.com.ar/tiendas/{store_id}-turbo-express/{base_category}"
    data = get_next_data(session, url)
    if not data:
        return [], None

    fallback = data.get("props", {}).get("pageProps", {}).get("fallback", {})
    store_name = None
    store_context = data.get("props", {}).get("pageProps", {}).get("storeContext")
    if store_context:
        store_name = store_context.get("address") or store_context.get("name")

    subcats = []
    for payload in fallback.values():
        sar = payload.get("sub_aisles_response")
        if not sar:
            continue
        for h in sar.get("data", {}).get("headers", []):
            cats = h.get("resource", {}).get("categories", [])
            for c in cats:
                name = c.get("name")
                # friendly_url no siempre viene en headers; lo derivamos por slugificación simple
                slug = c.get("friendly_url") or slugify(name)
                subcats.append((name, slug))

    return subcats, store_name


def slugify(text):
    text = text.lower()
    replacements = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n"}
    for a, b in replacements.items():
        text = text.replace(a, b)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text


def scrape_store(session, store_id, base_category="cervezas"):
    print(f"[store {store_id}] descargando categoría '{base_category}'...")
    url = f"https://www.rappi.com.ar/tiendas/{store_id}-turbo-express/{base_category}"
    data = get_next_data(session, url)
    if not data:
        print(f"[store {store_id}] no se pudo obtener la página principal de {base_category}")
        return []

    fallback = data.get("props", {}).get("pageProps", {}).get("fallback", {})
    store_context = data.get("props", {}).get("pageProps", {}).get("storeContext") or {}
    store_address = store_context.get("address", "")

    all_products = {}
    for p in extract_products_from_fallback(fallback):
        all_products[p["product_id"]] = p

    subcats, _ = get_subcategories(session, store_id, base_category)
    print(f"[store {store_id}] {len(subcats)} subcategorías encontradas: "
          f"{', '.join(n for n, _ in subcats)}")

    for name, slug in subcats:
        sub_url = f"https://www.rappi.com.ar/tiendas/{store_id}-turbo-express/{base_category}/{slug}"
        sub_data = get_next_data(session, sub_url)
        if not sub_data:
            print(f"    [!] no se pudo bajar subcategoría '{name}' ({slug})")
            continue
        sub_fallback = sub_data.get("props", {}).get("pageProps", {}).get("fallback", {})
        prods = extract_products_from_fallback(sub_fallback)
        for p in prods:
            all_products[p["product_id"]] = p
        print(f"    - {name}: {len(prods)} productos (acumulado único: {len(all_products)})")

    rows = []
    for p in all_products.values():
        attrs = p.get("attributes") or {}
        cold = bool(attrs.get("cold_beer"))
        rows.append({
            "store_id": store_id,
            "store_address": store_address,
            "product_id": p.get("product_id"),
            "sku_id": p.get("id"),
            "master_product_id": p.get("master_product_id"),
            "name": p.get("name"),
            "trademark": p.get("trademark"),
            "presentation": p.get("presentation"),
            "price": p.get("price"),
            "in_stock": p.get("in_stock"),
            "category_name": p.get("category_name"),
            "cold_beer": cold,
        })
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--store-ids", type=str, default=None,
                         help="Lista de store_id separados por coma. Si no se pasa, se lee stores.json")
    parser.add_argument("--category", type=str, default="cervezas",
                         help="Slug de categoría a scrapear (default: cervezas)")
    parser.add_argument("--out", type=str, default="cervezas_frias_rappi.csv")
    args = parser.parse_args()

    if args.store_ids:
        store_ids = [int(s.strip()) for s in args.store_ids.split(",") if s.strip()]
    else:
        with open("stores.json", encoding="utf-8") as f:
            store_ids = [s["store_id"] for s in json.load(f)]

    print(f"Store IDs a scrapear ({len(store_ids)}): {store_ids}")

    session = requests.Session()
    all_rows = []
    for i, store_id in enumerate(store_ids, 1):
        print(f"\n=== [{i}/{len(store_ids)}] store_id={store_id} ===")
        try:
            rows = scrape_store(session, store_id, args.category)
            all_rows.extend(rows)
        except Exception as e:
            print(f"[!] Error scrapeando store {store_id}: {e}")
        time.sleep(random.uniform(*REQUEST_DELAY_RANGE))

    if not all_rows:
        print("No se obtuvieron productos.")
        return

    fieldnames = list(all_rows[0].keys())
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    cold_count = sum(1 for r in all_rows if r["cold_beer"])
    print(f"\nListo. {len(all_rows)} SKUs totales, {cold_count} con badge de Frío.")
    print(f"Guardado en {args.out}")


if __name__ == "__main__":
    main()
