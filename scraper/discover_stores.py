"""
Paso 1: Descubre los store_id de Rappi Turbo (turbo-express) que cubren
Buenos Aires, probando una grilla/lista de direcciones y viendo qué
tienda Turbo asigna Rappi a cada una.

Uso:
    python discover_stores.py

Guarda el resultado en stores.json: [{"store_id": 266928, "seen_at": "Palermo Soho, Serrano"}, ...]
"""
import json
import random
import time
from playwright.sync_api import sync_playwright


def is_rate_limited(page):
    try:
        content = page.content()
    except Exception:
        return False
    return "429 Too Many Requests" in content or "Too Many Requests" in content

# Direcciones candidatas repartidas por barrios de CABA (se puede ampliar/ajustar).
# Rappi resuelve cada dirección a la tienda Turbo (dark store) más cercana que
# le hace envíos; probando muchas direcciones repartidas por la ciudad vamos
# descubriendo todos los store_id distintos que existen.
CANDIDATE_ADDRESSES = [
    "Palermo Soho, Serrano, Buenos Aires",
    "Belgrano, Buenos Aires",
    "Recoleta, Buenos Aires",
    "Villa Crespo, Buenos Aires",
    "Caballito, Buenos Aires",
    "Almagro, Buenos Aires",
    "Flores, Buenos Aires",
    "Villa Urquiza, Buenos Aires",
    "Colegiales, Buenos Aires",
    "Chacarita, Buenos Aires",
    "Nuñez, Buenos Aires",
    "Saavedra, Buenos Aires",
    "Coghlan, Buenos Aires",
    "Villa Devoto, Buenos Aires",
    "Villa del Parque, Buenos Aires",
    "Floresta, Buenos Aires",
    "Mataderos, Buenos Aires",
    "Liniers, Buenos Aires",
    "Parque Patricios, Buenos Aires",
    "Boedo, Buenos Aires",
    "San Cristobal, Buenos Aires",
    "Balvanera, Buenos Aires",
    "Monserrat, Buenos Aires",
    "San Telmo, Buenos Aires",
    "La Boca, Buenos Aires",
    "Barracas, Buenos Aires",
    "Puerto Madero, Buenos Aires",
    "Retiro, Buenos Aires",
    "Constitucion, Buenos Aires",
    "Once, Buenos Aires",
    "Palermo Hollywood, Buenos Aires",
    "Las Cañitas, Buenos Aires",
    "Villa Pueyrredon, Buenos Aires",
    "Villa Ortuzar, Buenos Aires",
    "Parque Chas, Buenos Aires",
    "Agronomia, Buenos Aires",
    "Paternal, Buenos Aires",
    "Versalles, Buenos Aires",
    "Velez Sarsfield, Buenos Aires",
    "Monte Castro, Buenos Aires",
]

OUTPUT_FILE = "stores.json"


def discover(addresses=None, resume=True):
    addresses = addresses if addresses is not None else CANDIDATE_ADDRESSES
    found = {}  # store_id -> info
    if resume:
        try:
            with open(OUTPUT_FILE, encoding="utf-8") as f:
                for s in json.load(f):
                    found[s["store_id"]] = s
            print(f"Reanudando: {len(found)} locales ya conocidos desde {OUTPUT_FILE}")
        except FileNotFoundError:
            pass
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="es-AR")
        page = context.new_page()
        page.goto("https://www.rappi.com.ar", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Cerrar banner de cookies si aparece
        try:
            page.click("text=Ok, entendido", timeout=3000)
        except Exception:
            pass

        for address in addresses:
            for attempt in range(1, 4):
                try:
                    if is_rate_limited(page):
                        wait = 30 * attempt
                        print(f"[429] rate limited antes de '{address}', esperando {wait}s...")
                        time.sleep(wait)
                        page.goto("https://www.rappi.com.ar/", wait_until="domcontentloaded")
                        page.wait_for_timeout(1500)
                        continue

                    store_ids = resolve_address_to_stores(page, address)

                    if is_rate_limited(page):
                        wait = 30 * attempt
                        print(f"[429] rate limited durante '{address}', esperando {wait}s y reintentando...")
                        time.sleep(wait)
                        page.goto("https://www.rappi.com.ar/", wait_until="domcontentloaded")
                        page.wait_for_timeout(1500)
                        continue

                    for sid in store_ids:
                        if sid not in found:
                            found[sid] = {"store_id": sid, "seen_at": address}
                            print(f"[+] Nuevo local encontrado: store_id={sid} (via '{address}')")
                        else:
                            print(f"    (ya conocido store_id={sid} para '{address}')")
                    break
                except Exception as e:
                    print(f"[!] Error con dirección '{address}' (intento {attempt}): {e}")
                    # Recuperación: recargar la home por si quedó un modal trabado
                    try:
                        page.goto("https://www.rappi.com.ar/", wait_until="domcontentloaded")
                        page.wait_for_timeout(1500)
                    except Exception:
                        pass
                    time.sleep(5)
            # Guardado incremental por si el proceso se corta a mitad de camino
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(list(found.values()), f, ensure_ascii=False, indent=2)
            time.sleep(random.uniform(4, 7))

        browser.close()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(list(found.values()), f, ensure_ascii=False, indent=2)
    print(f"\nTotal de locales Turbo distintos encontrados: {len(found)}")
    print(f"Guardado en {OUTPUT_FILE}")


ADDRESS_BUTTON_SEL = '[class*="AddressButtonContainer"]'
ADDRESS_INPUT_SEL = 'input[placeholder="Escribí la dirección de entrega"]'
SUGGESTION_SEL = '.chakra-modal__body li'
CONFIRM_BTN_SEL = 'button:has-text("Confirmar dirección")'
SAVE_BTN_SEL = 'button:has-text("Guardar dirección")'
MORE_STORES_BTN_SEL = 'button:has-text("Ver más tiendas disponibles")'


def resolve_address_to_stores(page, address):
    """Ingresa una dirección vía el modal de header y devuelve los store_id de tipo turbo-express visibles."""
    page.click(ADDRESS_BUTTON_SEL, timeout=8000)
    page.wait_for_selector(ADDRESS_INPUT_SEL, timeout=8000)

    input_box = page.locator(ADDRESS_INPUT_SEL)
    input_box.click()
    input_box.fill("")
    input_box.type(address, delay=25)

    page.wait_for_selector(SUGGESTION_SEL, timeout=8000)
    page.wait_for_timeout(400)
    page.locator(SUGGESTION_SEL).first.click()

    # Pantalla "Verifica la ubicación" con mapa
    try:
        page.wait_for_selector(CONFIRM_BTN_SEL, timeout=5000)
        page.click(CONFIRM_BTN_SEL)
    except Exception:
        pass

    # Pantalla "Agregar dirección" (piso/etiqueta opcional)
    try:
        page.wait_for_selector(SAVE_BTN_SEL, timeout=5000)
        page.click(SAVE_BTN_SEL)
    except Exception:
        pass

    page.wait_for_timeout(1200)

    # Si la tienda actual no hace envíos a la nueva dirección, aparece un modal
    try:
        page.wait_for_selector(MORE_STORES_BTN_SEL, timeout=3000)
        page.click(MORE_STORES_BTN_SEL)
        page.wait_for_timeout(1500)
    except Exception:
        pass

    # La home genérica (food delivery) no lista las tiendas de mercado/express.
    # Hay que ir al listado de mercados, que sí incluye la sección Express (Turbo).
    page.goto("https://www.rappi.com.ar/tiendas/tipo/market", wait_until="networkidle")
    page.wait_for_timeout(1000)

    # La lista de tiendas es virtualizada: hay que scrollear de a poco, con
    # espera suficiente, para que React monte en el DOM las secciones de más
    # abajo (Express / Turbo). Si se scrollea muy rápido se pasa de largo la
    # sección antes de que llegue a renderizar.
    hrefs = set()
    stable_checks = 0
    for _ in range(40):
        current = set(page.eval_on_selector_all(
            'a[href*="turbo-express"]',
            "els => els.map(e => e.getAttribute('href'))"
        ))
        if current:
            hrefs.update(current)
            stable_checks += 1
            if stable_checks >= 3:
                break
        else:
            stable_checks = 0
        page.mouse.wheel(0, 350)
        page.wait_for_timeout(500)
    store_ids = set()
    for href in hrefs:
        try:
            part = href.split("/tiendas/")[1]
            sid = int(part.split("-")[0])
            store_ids.add(sid)
        except Exception:
            continue
    return store_ids


if __name__ == "__main__":
    discover()
