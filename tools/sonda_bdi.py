"""Sonda 2: lê o JS do BDI (arquivos.b3.com.br/bdi) para achar as tabelas e o formato da chamada; testa POST."""

import json
import re
from datetime import date, timedelta

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
s = requests.Session()
s.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*", "Origin": "https://arquivos.b3.com.br",
                  "Referer": "https://arquivos.b3.com.br/bdi/tabelas?lang=pt-BR"})
base = "https://arquivos.b3.com.br"
idx = s.get(base + "/bdi/tabelas?lang=pt-BR", timeout=40).text
scripts = sorted(set(re.findall(r'src="([^"]+\.js[^"]*)"', idx)))
print("SCRIPTS", scripts)
names = set()
for src in scripts:
    u = src if src.startswith("http") else base + (src if src.startswith("/") else "/bdi/" + src)
    try:
        js = s.get(u, timeout=60).text
    except Exception as e:
        print("JSERR", u, e); continue
    print("JS", u, len(js))
    for pat in (r"bdi/table[^\"'`]{0,120}", r"\bapi/[^\"'`]{0,120}", r"method:\s*[\"'][A-Z]+[\"']", r"\.post\([^)]{0,160}", r"fetch\([^)]{0,160}"):
        for m in list(re.finditer(pat, js))[:15]:
            print(f"  HIT[{pat[:12]}] {js[max(0, m.start() - 160):m.end() + 160]!r}")
    for m in re.finditer(r'["\']([A-Z][A-Za-z]{6,60})["\']', js):
        if re.search(r"Renda|Fixa|Deb|CRA|CRI|Balc|Negoc|Privad|Titul", m.group(1)):
            names.add(m.group(1))
print("NAMES", sorted(names)[:150])
d = date.today() - timedelta(days=1)
while d.weekday() >= 5:
    d -= timedelta(days=1)
D = d.isoformat()
for nm in (sorted(names)[:40] or ["RendaFixaPrivada"]):
    u = f"{base}/bdi/table/{nm}/{D}/{D}/1/20"
    for body in ({}, {"Name": nm}):
        try:
            x = s.post(u, json=body, timeout=40)
            print("POST", x.status_code, nm, json.dumps(body), x.headers.get("content-type"), x.text[:400].replace("\n", " "))
            if x.status_code == 200:
                break
        except Exception as e:
            print("POSTERR", nm, e)
