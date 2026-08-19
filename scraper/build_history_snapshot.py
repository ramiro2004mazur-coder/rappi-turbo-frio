"""
Toma el CSV recién scrapeado (mismo formato que produce scrape_beers.py) y
suma un registro por darkstore a data/history.json — el archivo que acumula
la evolución de SKU en frío día a día para el dashboard.

No pisa fechas anteriores: si ya existe un registro para la misma fecha +
local, lo reemplaza (para que correr el script dos veces el mismo día no
duplique datos); todo lo demás queda intacto.

Uso:
    python scraper/build_history_snapshot.py --csv data/cervezas_frias_rappi.csv --date 2026-08-14
    (si no se pasa --date, usa la fecha de hoy)
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
import build_dashboard_data as bd

HISTORY_PATH = os.environ.get("HISTORY_JSON", "data/history.json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="data/cervezas_frias_rappi.csv")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    import csv
    with open(args.csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    agg = defaultdict(lambda: {"cold_total": 0, "cold_cmq": 0, "skus": []})
    for r in rows:
        if r["cold_beer"] != "True":
            continue
        store_id = int(r["store_id"])
        brand = bd.normalize_brand(r["trademark"], r["name"])
        is_cmq = brand in bd.CMQ_BRANDS
        agg[store_id]["cold_total"] += 1
        if is_cmq:
            agg[store_id]["cold_cmq"] += 1
        price = None
        try:
            price = float(r["price"]) if r["price"] else None
        except ValueError:
            pass
        agg[store_id]["skus"].append({
            "product_id": r["product_id"],
            "name": r["name"],
            "brand": brand,
            "is_cmq": is_cmq,
            "price": price,
            "presentation": r["presentation"],
        })

    new_entries = [
        {
            "date": args.date, "store_id": sid,
            "cold_total": v["cold_total"], "cold_cmq": v["cold_cmq"],
            "skus": v["skus"],
        }
        for sid, v in sorted(agg.items())
    ]

    try:
        with open(HISTORY_PATH, encoding="utf-8") as f:
            history = json.load(f)
    except FileNotFoundError:
        history = []

    # Saca cualquier registro previo de esta misma fecha (para poder re-correr
    # el mismo día sin duplicar), y suma los nuevos.
    history = [h for h in history if h["date"] != args.date]
    history.extend(new_entries)
    history.sort(key=lambda h: (h["date"], h["store_id"]))

    os.makedirs(os.path.dirname(HISTORY_PATH) or ".", exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    n_dates = len(set(h["date"] for h in history))
    print(f"{len(new_entries)} locales con frío el {args.date}.")
    print(f"{HISTORY_PATH} ahora tiene {len(history)} registros en total, de {n_dates} fecha(s) distintas.")


if __name__ == "__main__":
    main()
