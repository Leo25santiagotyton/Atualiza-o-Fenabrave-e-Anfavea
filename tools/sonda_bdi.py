"""Sonda: descobre a API do Boletim Diário do Mercado (BDI) da B3 com negócios de renda fixa privada (CRA/CRI/debêntures)."""

import re
from datetime import date, timedelta

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
s = requests.Session()
s.headers.update({"User-Agent": UA, "Accept": "*/*"})
PAGE = "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/consultas/boletim-diario/boletim-diario-do-mercado/"
r = s.get(PAGE, timeout=40)
print("PAGE", r.status_code, len(r.text))
for m in sorted(set(re.findall(r'(?:src|href|data-url|action)="([^"]+)"', r.text))):
    if re.search(r"bdi|boletim|arquivos\.b3|iframe|sistemas|api", m, re.I):
        print("LINK", m)
for m in re.finditer(r"<iframe[^>]+>", r.text):
    print("IFRAME", m.group(0)[:400])
for m in sorted(set(re.findall(r"https?://[a-z0-9.\-]+\.b3\.com\.br[^\"' <>]*", r.text)))[:80]:
    print("URL", m)

d = date.today() - timedelta(days=1)
while d.weekday() >= 5:
    d -= timedelta(days=1)
D = d.isoformat()
cands = [
    "https://arquivos.b3.com.br/bdi/table/tables",
    "https://arquivos.b3.com.br/bdi/table/list",
    f"https://arquivos.b3.com.br/bdi/download/bdi/{D}",
    f"https://arquivos.b3.com.br/bdi/table/RendaFixaPrivadaNegociosRealizados/{D}/{D}/1/100",
    f"https://arquivos.b3.com.br/bdi/table/NegociosRendaFixaPrivada/{D}/{D}/1/100",
    f"https://arquivos.b3.com.br/bdi/table/BalcaoRendaFixa/{D}/{D}/1/100",
    "https://arquivos.b3.com.br/bdi/",
    "https://arquivos.b3.com.br/apinegocios/",
]
for u in cands:
    try:
        x = s.get(u, timeout=40)
        print("TRY", x.status_code, x.headers.get("content-type"), u, x.text[:700].replace("\n", " "))
    except Exception as e:
        print("TRY ERRO", u, e)

# JS do site do BDI, se houver
for js in sorted(set(re.findall(r'src="([^"]+\.js[^"]*)"', r.text)))[:40]:
    u = js if js.startswith("http") else "https://www.b3.com.br" + js
    try:
        t = s.get(u, timeout=30).text
    except Exception:
        continue
    for m in re.finditer(r"(arquivos\.b3\.com\.br/[a-zA-Z0-9/_\-{}$.]+|bdi/table/[A-Za-z0-9_]+)", t):
        print("JSHIT", u.split("/")[-1][:40], m.group(1)[:200])
