"""Sonda 3: trecho do GetTablePaged e das funções que listam as tabelas do BDI; testa a listagem."""

import json
import re
from datetime import date, timedelta

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
s = requests.Session()
s.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*", "Origin": "https://arquivos.b3.com.br",
                  "Referer": "https://arquivos.b3.com.br/bdi/tabelas?lang=pt-BR", "Content-Type": "application/json"})
base = "https://arquivos.b3.com.br"
js = s.get(base + "/bdi/static/js/main.e591a35328ff179145c0.js", timeout=90).text
i = js.find("function GetTablePaged")
print("GETTABLEPAGED", js[max(0, i - 2500):i + 2500])
for fn in ("function GetTables", "function GetClassifications", "function GetTable(", "function GetGroups", "function GetMenu", "classificationsGet", "tables/"):
    for m in list(re.finditer(re.escape(fn), js))[:3]:
        print(f"FN[{fn}]", js[max(0, m.start() - 300):m.end() + 900].replace("\n", " "))
d = date.today() - timedelta(days=1)
while d.weekday() >= 5:
    d -= timedelta(days=1)
D = d.isoformat()
for u, method in [(f"{base}/bdi/table/tables", "POST"), (f"{base}/bdi/tables", "POST"), (f"{base}/bdi/table/classifications", "POST"),
                  (f"{base}/bdi/classification", "GET"), (f"{base}/bdi/table/list/{D}", "POST"), (f"{base}/bdi/menu", "GET"),
                  ("https://drp.b3.com.br/api/tables", "GET"), ("https://drp.b3.com.br/rapinegocios/dates?type=1", "GET")]:
    try:
        x = s.request(method, u, json={} if method == "POST" else None, timeout=40)
        print("TRY", method, x.status_code, u, x.headers.get("content-type"), x.text[:600].replace("\n", " "))
    except Exception as e:
        print("TRYERR", u, e)
