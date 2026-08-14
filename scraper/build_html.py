"""
Arma el dashboard final: toma dashboard/template.html y le inyecta
data/dashboard_data.json (el relevamiento del día) y data/history.json
(todo el histórico acumulado), y escribe el resultado en docs/index.html
— la carpeta que sirve GitHub Pages.
"""
import json
import os

TEMPLATE = "dashboard/template.html"
DASHBOARD_JSON = os.environ.get("DASHBOARD_JSON", "data/dashboard_data.json")
HISTORY_JSON = os.environ.get("HISTORY_JSON", "data/history.json")
OUT = "docs/index.html"


def main():
    with open(TEMPLATE, encoding="utf-8") as f:
        template = f.read()

    with open(DASHBOARD_JSON, encoding="utf-8") as f:
        dashboard_data = f.read()

    try:
        with open(HISTORY_JSON, encoding="utf-8") as f:
            history_data = f.read()
    except FileNotFoundError:
        history_data = "[]"

    def safe(s):
        return s.replace("</script>", "<\\/script>")

    html = template.replace("__DATA_JSON__", safe(dashboard_data))
    html = html.replace("__HISTORY_JSON__", safe(history_data))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)

    n_dates = len(set(h["date"] for h in json.loads(history_data))) if history_data.strip() != "[]" else 0
    print(f"{OUT} generado ({len(html):,} bytes), con {n_dates} fecha(s) de histórico.")


if __name__ == "__main__":
    main()
