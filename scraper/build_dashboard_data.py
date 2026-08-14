"""
Prepara los datos para el dashboard: normaliza marca, clasifica CMQ vs no-CMQ,
mapea cada store_id a nombre/ciudad/provincia, y exporta un JSON listo para
embeber en el HTML del dashboard.
"""
import csv
import json
import os
import re
import sys
from datetime import date

CSV_IN = os.environ.get("CERVEZAS_CSV", "data/cervezas_frias_rappi.csv")
JSON_OUT = os.environ.get("DASHBOARD_JSON", "data/dashboard_data.json")

# Fecha del relevamiento actual. Por default es "hoy" (para que corra sola en
# GitHub Actions); se puede forzar con --date=YYYY-MM-DD para pruebas manuales.
SCRAPE_DATE = date.today().isoformat()
for arg in sys.argv[1:]:
    if arg.startswith("--date="):
        SCRAPE_DATE = arg.split("=", 1)[1]

# --- Metadata de los 27 locales (lista provista por el usuario) ---
STORES = {
    166964: {"name": "Belgrano 1", "address": "Monroe 1616", "city": "CABA", "province": "CABA"},
    184221: {"name": "Forest", "address": "Forest 930", "city": "CABA", "province": "CABA"},
    184923: {"name": "Rivadavia", "address": "Av Rivadavia 8242", "city": "CABA", "province": "CABA"},
    184924: {"name": "San Juan", "address": "San Juan 3536", "city": "CABA", "province": "CABA"},
    185340: {"name": "Monserrat", "address": "Av. Belgrano 1154", "city": "CABA", "province": "CABA"},
    185458: {"name": "Baez", "address": "Baez 243", "city": "CABA", "province": "CABA"},
    185460: {"name": "Peron", "address": "Tte Gral Perón 3341", "city": "CABA", "province": "CABA"},
    186262: {"name": "San Martín", "address": "Av. S. Martín 2011", "city": "CABA", "province": "CABA"},
    186327: {"name": "Centenera", "address": "Centenera 193", "city": "CABA", "province": "CABA"},
    231868: {"name": "Las Heras", "address": "Av. Gral. Las Heras 2299", "city": "CABA", "province": "CABA"},
    266848: {"name": "Palermo", "address": "Av. Córdoba 5346", "city": "CABA", "province": "CABA"},
    266872: {"name": "San Nicolas", "address": "Lavalle 1521", "city": "CABA", "province": "CABA"},

    207836: {"name": "Mar del Plata", "address": "Belgrano 3434", "city": "Mar del Plata", "province": "Buenos Aires"},
    216336: {"name": "La Plata", "address": "55 661", "city": "La Plata", "province": "Buenos Aires"},
    224352: {"name": "Lomas de Zamora", "address": "Av. Hipólito Yrigoyen 7970, Banfield", "city": "Banfield", "province": "Buenos Aires"},
    228542: {"name": "Vicente Lopez", "address": "Av. Maipú 3131, Olivos", "city": "Olivos", "province": "Buenos Aires"},
    231507: {"name": "Ramos Mejía", "address": "Ricchieri 131, La Matanza", "city": "Ramos Mejía", "province": "Buenos Aires"},
    231869: {"name": "Villa Martelli", "address": "Zufriategui 3611", "city": "Villa Martelli", "province": "Buenos Aires"},
    232258: {"name": "Villa Lynch", "address": "Av. Guido Spano 3931", "city": "Villa Lynch", "province": "Buenos Aires"},
    240042: {"name": "Nordelta", "address": "Av. Agustín M. García 5599", "city": "Nordelta", "province": "Buenos Aires"},
    242531: {"name": "Beccar", "address": "Av. Andres Rolon 1979", "city": "Beccar", "province": "Buenos Aires"},
    244575: {"name": "Lanus", "address": "Av. Hipólito Yrigoyen 4306", "city": "Lanús", "province": "Buenos Aires"},
    244576: {"name": "Moron", "address": "Av. Brigadier Gral. J. M. de Rosas 588, Castelar", "city": "Castelar", "province": "Buenos Aires"},
    262497: {"name": "Avellaneda", "address": "Villegas 1245", "city": "Avellaneda", "province": "Buenos Aires"},

    234279: {"name": "Cordoba Centro", "address": "Int. Ramón Bautista Mestre 725", "city": "Córdoba", "province": "Córdoba"},
    255978: {"name": "Cerro de las Rosas", "address": "Carlos Federico Gauss 5231", "city": "Córdoba", "province": "Córdoba"},

    250388: {"name": "Rosario", "address": "Av. Ovidio Lagos 333", "city": "Rosario", "province": "Santa Fe"},
}

REGION = {
    "CABA": "CABA",
    "Mar del Plata": "Buenos Aires - Costa/Interior",
    "La Plata": "Buenos Aires - Interior",
    "Banfield": "GBA Sur",
    "Olivos": "GBA Norte",
    "Ramos Mejía": "GBA Oeste",
    "Villa Martelli": "GBA Norte",
    "Villa Lynch": "GBA Oeste",
    "Nordelta": "GBA Norte",
    "Beccar": "GBA Norte",
    "Lanús": "GBA Sur",
    "Castelar": "GBA Oeste",
    "Avellaneda": "GBA Sur",
    "Córdoba": "Córdoba",
    "Rosario": "Santa Fe",
}

# --- Clasificación de marcas: CMQ (Cervecería y Maltería Quilmes / AB InBev
# Argentina) vs. no-CMQ. Basado en conocimiento público de los portfolios de
# cada cervecería. Revisar / ajustar antes de presentar formalmente. ---

CMQ_BRANDS = {
    "Quilmes", "Brahma", "Stella Artois", "Budweiser", "Corona",
    "Michelob Ultra", "Patagonia", "Andes", "1890", "Norte", "Palermo",
    "Liberty",
}

BRAND_OWNER = {
    # CMQ / AB InBev Argentina
    "Quilmes": "CMQ (AB InBev)", "Brahma": "CMQ (AB InBev)", "Stella Artois": "CMQ (AB InBev)",
    "Budweiser": "CMQ (AB InBev)", "Corona": "CMQ (AB InBev)", "Michelob Ultra": "CMQ (AB InBev)",
    "Patagonia": "CMQ (AB InBev)", "Andes": "CMQ (AB InBev)", "1890": "CMQ (AB InBev)",
    # Heineken Argentina
    "Heineken": "Heineken Argentina", "Amstel": "Heineken Argentina", "Sol": "Heineken Argentina",
    # CCU Argentina
    "Schneider": "CCU Argentina", "Imperial": "CCU Argentina", "Salta": "CCU Argentina",
    "Salta Cautiva": "CCU Argentina", "Santa Fe": "CCU Argentina", "Kunstmann": "CCU Argentina",
    # Molson Coors
    "Miller": "Molson Coors", "Blue Moon": "Molson Coors",
    # Asahi Group
    "Grolsch": "Asahi Group", "Peroni": "Asahi Group", "Asahi": "Asahi Group",
    # Diageo
    "Guinness": "Diageo",
    # Independientes / importadas chicas
    "Antares": "Independiente (AR)", "Pampa": "Independiente (AR)", "Rabieta": "Independiente (AR)",
    "Temple": "Independiente (AR)", "Estrella Galicia": "Importada (España)",
    "Estrella Damm": "Importada (España)", "Bitburger": "Importada (Alemania)",
    "Kostritzer": "Importada (Alemania)", "Warsteiner": "Importada (Alemania)",
    "Konig Pilsener": "Importada (Alemania)",
}

# Normalización: variantes de un mismo nombre -> nombre canónico
BRAND_ALIASES = {
    "corona 0": "Corona", "stella artois 0": "Stella Artois", "quilmes 0": "Quilmes",
    "heineken cero": "Heineken", "andes origen": "Andes", "blonde": "Santa Fe",
    "pilsener konign": "Konig Pilsener", "guinnes": "Guinness",
}

# Para filas sin trademark: detectar marca a partir del nombre del producto.
# Orden importa: los patrones más específicos van primero.
NAME_BRAND_PATTERNS = [
    ("Salta Cautiva", r"salta\s+cautiva"),
    ("Quilmes", r"quilmes"),
    ("Stella Artois", r"stella\s*artois"),
    ("Budweiser", r"budweiser"),
    ("Corona", r"corona"),
    ("Michelob Ultra", r"michelob"),
    ("Patagonia", r"patagonia"),
    ("Andes", r"andes"),
    ("Brahma", r"brahma"),
    ("Heineken", r"heineken"),
    ("Amstel", r"amstel"),
    ("Schneider", r"schneider"),
    ("Imperial", r"imperial"),
    ("Salta", r"\bsalta\b"),
    ("Kunstmann", r"kunstmann"),
    ("Antares", r"antares"),
    ("Pampa", r"pampa"),
    ("Rabieta", r"rabieta"),
    ("Estrella Galicia", r"estrella\s*galicia"),
    ("Estrella Damm", r"estrella\s*damm"),
    ("Grolsch", r"grolsch"),
    ("Guinness", r"guinness|guinnes"),
    ("Bitburger", r"bitburger"),
    ("Kostritzer", r"kostritzer|köstritzer|kostritzer"),
    ("Warsteiner", r"warsteiner"),
    ("Peroni", r"peroni"),
    ("Miller", r"miller"),
    ("Blue Moon", r"blue\s*moon"),
    ("Asahi", r"asahi"),
    ("1890", r"\b1890\b"),
    ("Temple", r"\btemple\b"),
    ("Konig Pilsener", r"konig|könig"),
]


def normalize_brand(trademark, name):
    tm = (trademark or "").strip()
    if tm:
        key = tm.lower()
        if key in BRAND_ALIASES:
            return BRAND_ALIASES[key]
        return tm
    # sin trademark: buscar en el nombre del producto
    lname = name.lower()
    for brand, pattern in NAME_BRAND_PATTERNS:
        if re.search(pattern, lname):
            return brand
    return "Sin identificar"


def main():
    with open(CSV_IN, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    out_rows = []
    unknown_brands = set()
    missing_stores = set()

    for r in rows:
        store_id = int(r["store_id"])
        store_meta = STORES.get(store_id)
        if not store_meta:
            missing_stores.add(store_id)
            store_meta = {"name": f"Store {store_id}", "address": "", "city": "Desconocida", "province": "Desconocida"}

        brand = normalize_brand(r["trademark"], r["name"])
        if brand == "Sin identificar":
            unknown_brands.add(r["name"])

        is_cmq = brand in CMQ_BRANDS
        owner = BRAND_OWNER.get(brand, "Sin clasificar")

        price = None
        try:
            price = float(r["price"]) if r["price"] else None
        except ValueError:
            pass

        out_rows.append({
            "store_id": store_id,
            "store_name": store_meta["name"],
            "address": store_meta["address"],
            "city": store_meta["city"],
            "province": store_meta["province"],
            "region": REGION.get(store_meta["city"], store_meta["province"]),
            "product_id": r["product_id"],
            "name": r["name"],
            "brand": brand,
            "owner": owner,
            "is_cmq": is_cmq,
            "cold": r["cold_beer"] == "True",
            "in_stock": r["in_stock"] == "True",
            "price": price,
            "presentation": r["presentation"],
            "category_name": r["category_name"],
        })

    # Formato compacto: columnas + filas como arrays (en vez de objetos repetidos)
    columns = ["store_id", "store_name", "address", "province", "region", "name", "brand",
               "owner", "is_cmq", "cold", "in_stock", "price", "presentation"]
    compact_rows = [[r[c] for c in columns] for r in out_rows]

    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump({"meta": {"scrape_date": SCRAPE_DATE}, "columns": columns, "rows": compact_rows}, f, ensure_ascii=False)

    print(f"Filas procesadas: {len(out_rows)}")
    print(f"Locales sin metadata: {missing_stores}")
    print(f"Marcas sin identificar ({len(unknown_brands)} productos únicos):")
    for n in sorted(unknown_brands):
        print("  -", n)
    print(f"\nGuardado en {JSON_OUT}")


if __name__ == "__main__":
    main()
