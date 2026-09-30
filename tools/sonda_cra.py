"""Sonda: descobre os endpoints de CRI/CRA do portal data.anbima.com.br."""

import re

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
     "Accept": "application/json, text/plain, */*", "Origin": "https://data.anbima.com.br", "Referer": "https://data.anbima.com.br/"}
s = requests.Session()
s.headers.update(H)

pages = ["https://data.anbima.com.br/certificado-de-recebiveis/CRA023000MC/caracteristicas",
         "https://data.anbima.com.br/certificado-de-recebiveis/CRA023000MC",
         "https://data.anbima.com.br/certificado-de-recebiveis"]
scripts = set()
for u in pages:
    r = s.get(u, timeout=30)
    print("PAGE", u, r.status_code, len(r.content))
    scripts |= set(re.findall(r'src="(/_next/static/[^"]+\.js)"', r.text))
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    if m:
        print("NEXT_DATA", m.group(1)[:1500])

hits = set()
for src in sorted(scripts):
    js = s.get("https://data.anbima.com.br" + src, timeout=40).text
    for m in re.finditer(r"certificado|cri-cra|/cra|/cri|recebiveis", js, re.I):
        a, b = max(0, m.start() - 160), m.end() + 160
        frag = js[a:b].replace("\n", " ")
        if "http" in frag or "/api" in frag or "fetch" in frag or "`" in frag:
            hits.add(frag)
    for m in re.finditer(r'["\'`](/[a-z0-9\-/]*(?:cri|cra|certificad|receb)[a-z0-9\-/${}.]*)["\'`]', js, re.I):
        hits.add("PATH " + m.group(1))
print("SCRIPTS", len(scripts))
for h in sorted(hits)[:80]:
    print("HIT", h[:360])

base = "https://data-api.prd.anbima.com.br"
for path in ["/web-bff/v1/certificados-recebiveis/CRA023000MC", "/web-bff/v1/cri-cra/CRA023000MC",
             "/web-bff/v1/certificado-de-recebiveis/CRA023000MC/precos", "/data-api/v1/cri-cra/precos?codigo=CRA023000MC",
             "/web-bff/v1/cri-cra/precos?page=0&size=5"]:
    try:
        r = s.get(base + path, timeout=30)
        print("API", path, r.status_code, r.headers.get("content-type"), r.text[:400].replace("\n", " "))
    except Exception as e:
        print("API", path, "ERRO", e)
