"""Sonda: descobre como o portal data.anbima.com.br autentica a API de CRI/CRA e onde há arquivo público."""

import re

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
     "Accept": "application/json, text/plain, */*", "Origin": "https://data.anbima.com.br", "Referer": "https://data.anbima.com.br/"}
s = requests.Session()
s.headers.update(H)

r = s.get("https://data.anbima.com.br/certificado-de-recebiveis/CRA023000MC/caracteristicas", timeout=30)
print("PAGE", r.status_code, len(r.content), dict(r.cookies))
scripts = sorted(set(re.findall(r'src="(/_next/static/[^"]+\.js)"', r.text)))
print("SCRIPTS", len(scripts))
seen = set()
for src in scripts:
    js = s.get("https://data.anbima.com.br" + src, timeout=40).text
    for pat in (r"web-bff", r"[Tt]oken", r"access_token", r"client_id", r"x-api", r"Authorization", r"recaptcha", r"TaxasCriCra", r"downloadExterno"):
        for m in list(re.finditer(pat, js))[:12]:
            frag = js[max(0, m.start() - 220):m.end() + 220].replace("\n", " ")
            k = frag[180:260]
            if k in seen:
                continue
            seen.add(k)
            print(f"HIT[{pat}] {src.split('/')[-1]}: {frag}")

for u in ["https://www.anbima.com.br/pt_br/informar/precos-e-indices/precos/taxas-de-cri-e-cra.htm",
          "https://www.anbima.com.br/pt_br/informar/taxas-de-cri-e-cra.htm",
          "https://www.anbima.com.br/informacoes/cri-cra/default.asp"]:
    try:
        r = requests.get(u, headers={"User-Agent": H["User-Agent"]}, timeout=30)
        links = sorted(set(re.findall(r'(?:href|src|action)="([^"]*(?:cri|cra|CRI|CRA)[^"]*)"', r.text)))
        print("WWW", u, r.status_code, len(r.content), links[:40])
    except Exception as e:
        print("WWW", u, "ERRO", e)

base = "https://data-api.prd.anbima.com.br"
for path in ["/web-bff/v1/certificado-recebiveis?page=0&size=5",
             "/web-bff/v1/certificado-recebiveis/CRA023000MC",
             "/web-bff/v1/certificado-recebiveis/CRA023000MC/caracteristicas",
             "/web-bff/v1/certificado-recebiveis/precos?page=0&size=5",
             "/web-bff/v1/TaxasCriCraExport/downloadExterno"]:
    try:
        r = s.get(base + path, timeout=30)
        print("API", path, r.status_code, r.headers.get("content-type"), r.text[:300].replace("\n", " "))
    except Exception as e:
        print("API", path, "ERRO", e)
