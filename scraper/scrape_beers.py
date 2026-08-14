"""
Scraper de cervezas de Rappi Turbo — versión con navegador real (Playwright).

Por qué con navegador y no con requests: cada subcategoría de "Cervezas"
(ej. "Cervezas Rubias") solo entrega ~24 productos en la carga inicial de la
página, aunque tenga muchos más (ej. 75). El resto se carga haciendo click en
el botón "Ver más", que dispara un POST a un endpoint interno de Rappi
(services.rappi.com.ar/.../dynamic/context/content/) que exige un "device id"
generado por el propio navegador — no se puede replicar de forma simple ni
confiable solo con HTTP. Por eso este scraper usa un navegador real, entra a
cada subcategoría y clickea "Ver más" hasta agotarla, capturando las
respuestas de red reales para no perderse ningún SKU.

Uso:
    python scraper/scrape_beers.py --store-ids 266928,185472 --out data/cervezas_frias_rappi.csv
"""
import argparse
import csv
import re
import time

from playwright.sync_api import sync_playwright

BASE = "https://www.rappi.com.ar"
MAX_VER_MAS_CLICKS = 25  # tope de seguridad por subcategoría
REQUEST_DELAY = 1.2      # pausa entre acciones, para no forzar el sitio


def slugify(text):
    text = text.lower()
    for a, b in {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n"}.items():
        text = text.replace(a, b)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text


def scrape_store(page, store_id, category_slug="cervezas"):
    url = f"{BASE}/tiendas/{store_id}-turbo-express/{category_slug}"
    page.goto(url, wait_until="networkidle", timeout=45000)

    next_data = page.evaluate(
        "() => JSON.parse(document.getElementById('__NEXT_DATA__').textContent)"
    )
    pageProps = next_data["props"]["pageProps"]
    fallback = pageProps.get("fallback", {})
    fbkey = next(iter(fallback), None)
    store_context = pageProps.get("storeContext", {}) or {}
    store_address = store_context.get("address", "")

    all_products = {}
    subcats = []
    if fbkey:
        sar = fallback[fbkey].get("sub_aisles_response", {}).get("data", {})
        for h in sar.get("headers", []):
            for c in h.get("resource", {}).get("categories", []):
                subcats.append({"id": c["id"], "name": c["name"]})
        for comp in sar.get("components", []):
            for p in comp.get("resource", {}).get("products", []):
                all_products[p["product_id"]] = p

    print(f"[store {store_id}] {len(subcats)} subcategorías: {', '.join(s['name'] for s in subcats)}")

    for sub in subcats:
        slug = slugify(sub["name"])
        sub_url = f"{url}/{slug}"
        before = len(all_products)

        def handle_response(response, _bucket=all_products):
            if "dynamic/context/content" not in response.url:
                return
            try:
                req_body = response.request.post_data or ""
                if '"aisle_detail"' not in req_body:
                    return
                data = response.json()
                for comp in data.get("data", {}).get("components", []):
                    for p in comp.get("resource", {}).get("products", []):
                        _bucket[p["product_id"]] = p
            except Exception:
                pass

        page.on("response", handle_response)
        try:
            page.goto(sub_url, wait_until="networkidle", timeout=45000)
        except Exception as e:
            print(f"    [!] no se pudo cargar subcategoría '{sub['name']}': {e}")
            page.remove_listener("response", handle_response)
            continue

        # capturar lo que ya vino en la carga inicial de la subcategoría
        try:
            sub_next_data = page.evaluate(
                "() => JSON.parse(document.getElementById('__NEXT_DATA__').textContent)"
            )
            sub_fallback = sub_next_data["props"]["pageProps"].get("fallback", {})
            sub_fbkey = next(iter(sub_fallback), None)
            if sub_fbkey:
                ad = sub_fallback[sub_fbkey].get("aisle_detail_response", {}).get("data", {})
                for comp in ad.get("components", []):
                    for p in comp.get("resource", {}).get("products", []):
                        all_products[p["product_id"]] = p
        except Exception:
            pass

        clicks = 0
        for _ in range(MAX_VER_MAS_CLICKS):
            count_before = page.locator('a[href^="/p/"]').count()
            clicked = page.evaluate(
                """() => {
                    const btn = Array.from(document.querySelectorAll('button, a'))
                        .find(el => /ver\\s*m[aá]s/i.test(el.textContent || ''));
                    if (!btn) return false;
                    btn.click();
                    return true;
                }"""
            )
            if not clicked:
                break
            clicks += 1
            # el contenido nuevo puede tardar unos segundos en aparecer:
            # sondeamos hasta 8s en vez de esperar un tiempo fijo.
            grew = False
            for _ in range(16):
                page.wait_for_timeout(500)
                if page.locator('a[href^="/p/"]').count() > count_before:
                    grew = True
                    break
            if not grew:
                break

        page.remove_listener("response", handle_response)
        gained = len(all_products) - before
        print(f"    - {sub['name']}: {gained} productos ({clicks} click(s) en 'Ver más')")
        time.sleep(REQUEST_DELAY)

    return list(all_products.values()), store_address


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--store-ids", type=str, required=True)
    parser.add_argument("--category", type=str, default="cervezas")
    parser.add_argument("--out", type=str, default="data/cervezas_frias_rappi.csv")
    args = parser.parse_args()

    store_ids = [int(s.strip()) for s in args.store_ids.split(",") if s.strip()]
    print(f"Store IDs a scrapear ({len(store_ids)}): {store_ids}")

    all_rows = []
    failed_stores = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="es-AR")
        page = context.new_page()

        for i, store_id in enumerate(store_ids, 1):
            print(f"\n=== [{i}/{len(store_ids)}] store_id={store_id} ===")
            products, store_address = None, ""
            for attempt in range(1, 4):
                try:
                    products, store_address = scrape_store(page, store_id, args.category)
                    break
                except Exception as e:
                    print(f"[!] Error scrapeando store {store_id} (intento {attempt}/3): {e}")
                    # la página puede haber quedado en un estado roto (navegación
                    # interrumpida): la recreamos antes de reintentar.
                    try:
                        page.close()
                    except Exception:
                        pass
                    time.sleep(4 * attempt)
                    page = context.new_page()
            if products is None:
                failed_stores.append(store_id)
                continue
            time.sleep(REQUEST_DELAY)

            for p_ in products:
                attrs = p_.get("attributes") or {}
                cold = bool(attrs.get("cold_beer"))
                all_rows.append({
                    "store_id": store_id,
                    "store_address": store_address,
                    "product_id": p_.get("product_id"),
                    "sku_id": p_.get("id"),
                    "master_product_id": p_.get("master_product_id"),
                    "name": p_.get("name"),
                    "trademark": p_.get("trademark"),
                    "presentation": p_.get("presentation"),
                    "price": p_.get("price"),
                    "in_stock": p_.get("in_stock"),
                    "category_name": p_.get("category_name"),
                    "cold_beer": cold,
                })

        browser.close()

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
    if failed_stores:
        print(f"[!] {len(failed_stores)} local(es) no se pudieron scrapear tras 3 intentos: {failed_stores}")
    print(f"Guardado en {args.out}")


if __name__ == "__main__":
    main()
