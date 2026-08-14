# Frío en Rappi Turbo

Dashboard que mide qué SKU de cerveza tienen el badge de "entrega en frío" en
Rappi Turbo, comparando marcas de CMQ (Cervecería y Maltería Quilmes / AB InBev
Argentina) contra el resto, en los 27 darkstores relevados.

## Cómo funciona (automático)

Todos los días a las **9:00 AM hora Argentina**, GitHub Actions:

1. Scrapea los 27 darkstores (`scraper/scrape_beers.py`).
2. Clasifica cada SKU por marca / CMQ (`scraper/build_dashboard_data.py`).
3. Suma el día al histórico acumulado, sin pisar días anteriores
   (`scraper/build_history_snapshot.py` → `data/history.json`).
4. Reconstruye el dashboard (`scraper/build_html.py` → `docs/index.html`).
5. Sube los cambios al repositorio automáticamente.

GitHub Pages publica `docs/index.html` en una URL fija — no hace falta que
nadie toque nada para que se actualice.

Ver el estado de las corridas / dispararla a mano: pestaña **Actions** de este
repositorio → "Scrapeo diario y publicación del dashboard" → **Run workflow**.

## Estructura

```
scraper/
  scrape_beers.py           scraper de producto (requests, sin browser)
  discover_stores.py        descubre store_id nuevos (Playwright — uso manual, no corre solo)
  build_dashboard_data.py   normaliza marca + clasifica CMQ, arma dashboard_data.json
  build_history_snapshot.py suma el día de hoy a data/history.json
  build_html.py             arma docs/index.html final
dashboard/
  template.html             plantilla del dashboard (HTML+CSS+JS)
data/
  cervezas_frias_rappi.csv  último scrapeo crudo (se sobreescribe cada día)
  dashboard_data.json       datos del día, procesados
  history.json              histórico acumulado (nunca se pisa entero)
docs/
  index.html                el dashboard publicado por GitHub Pages
```

## Correrlo a mano (para pruebas)

```bash
pip install -r requirements.txt
python scraper/scrape_beers.py --store-ids 166964,184221,184923,184924,185340,185458,185460,186262,186327,207836,216336,224352,228542,231507,231868,231869,232258,234279,240042,242531,244575,244576,250388,255978,262497,266848,266872 --out data/cervezas_frias_rappi.csv
python scraper/build_dashboard_data.py
python scraper/build_history_snapshot.py --csv data/cervezas_frias_rappi.csv
python scraper/build_html.py
```

## Si algún día hay que agregar/sacar un darkstore

La lista de los 27 `store_id` vive en dos lugares que hay que mantener
sincronizados: `scraper/build_dashboard_data.py` (diccionario `STORES`, con
nombre/dirección/provincia) y el comando `--store-ids` dentro de
`.github/workflows/daily-scrape.yml`. `scraper/discover_stores.py` sirve para
volver a descubrir locales por dirección si hace falta (requiere
`pip install playwright && playwright install chromium`, no se corre solo).
