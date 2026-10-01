"""Sonda 4: lista as tabelas do BDI (GET /bdi/table/classifications) e busca as de renda fixa privada."""

import json
import re
from datetime import date, timedelta

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
s = requests.Session()
s.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*", "Referer": "https://arquivos.b3.com.br/bdi/tabelas?lang=pt-BR"})
SRV = "https://arquivos.b3.com.br/bdi"
cfg = s.get(SRV + "/config.js", timeout=30).text
print("CONFIG", re.findall(r"serverUrl[^,\n]*", cfg))
r = s.get(SRV + "/table/classifications", timeout=40)
print("CLASS", r.status_code, r.headers.get("content-type"), len(r.text))
data = r.json() if "json" in (r.headers.get("content-type") or "") else None
tables = []
def walk(o, path=""):
    if isinstance(o, dict):
        nm = o.get("name") or o.get("Name")
        fr = o.get("friendlyNamePt") or o.get("friendlyName") or o.get("FriendlyName")
        if nm and fr:
            tables.append((nm, fr, path))
        for k, v in o.items():
            walk(v, path + "/" + str(o.get("friendlyNamePt") or o.get("name") or k)[:40] if isinstance(v, (list, dict)) else path)
    elif isinstance(o, list):
        for v in o:
            walk(v, path)
walk(data)
print("NTABLES", len(tables))
for nm, fr, path in tables:
    print("TABLE", nm, "|", fr, "|", path[-120:])
if not tables:
    print("RAW", r.text[:3000])
d = date.today() - timedelta(days=1)
while d.weekday() >= 5:
    d -= timedelta(days=1)
D = d.isoformat()
pick = [t for t in tables if re.search(r"renda fixa|deb[eê]nt|CRA|CRI|certificad|balc|privad|t[ií]tulos", (t[1] + " " + t[0] + " " + t[2]), re.I)][:25]
for nm, fr, _ in pick:
    u = f"{SRV}/table/{nm}/{D}/{D}/1/20"
    try:
        x = s.post(u, json={}, headers={"Content-Type": "application/json"}, timeout=60)
        j = x.json()
        t = j.get("table", j)
        cols = [c.get("friendlyNamePt") or c.get("name") for c in (t.get("columns") or [])] if isinstance(t, dict) else None
        vals = t.get("values") if isinstance(t, dict) else None
        print("DATA", x.status_code, nm, "|", fr, "| cols", cols, "| n", len(vals or []), "| ex", json.dumps((vals or [])[:3], ensure_ascii=False)[:900])
    except Exception as e:
        print("DATAERR", nm, e, x.text[:300] if 'x' in dir() else "")
