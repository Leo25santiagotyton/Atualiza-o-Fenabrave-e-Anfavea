"""Sonda: descobre como o portal data.anbima.com.br autentica a API de CRI/CRA e onde há arquivo público."""

import re

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
H = {"User-Agent": UA, "Accept": "application/json, text/plain, */*", "Origin": "https://data.anbima.com.br", "Referer": "https://data.anbima.com.br/"}
s = requests.Session()
s.headers.update(H)

r = s.get("https://data.anbima.com.br/certificado-de-recebiveis/CRA023000MC/caracteristicas", headers={"Accept": "text/html"}, timeout=30)
print("PAGE", r.status_code, r.headers.get("content-type"))
print(r.text[:5000])
srcs = sorted(set(re.findall(r'(?:src|href)="([^"]+\.(?:js|json)[^"]*)"', r.text)))
print("SRCS", srcs)
for src in srcs:
    u = src if src.startswith("http") else "https://data.anbima.com.br" + ("" if src.startswith("/") else "/") + src
    try:
        js = s.get(u, timeout=40).text
    except Exception as e:
        print("JS ERRO", u, e)
        continue
    print("JS", u, len(js))
    for pat in (r"web-bff", r"[Tt]oken", r"client_id", r"Authorization", r"recaptcha", r"access_token", r"x-api-key", r"apiKey"):
        for m in list(re.finditer(pat, js))[:8]:
            print(f"  HIT[{pat}]: {js[max(0, m.start() - 200):m.end() + 200]!r}")
    for sub in sorted(set(re.findall(r'["\'](/?(?:assets|static|_next)/[^"\']+\.js)["\']', js)))[:60]:
        u2 = "https://data.anbima.com.br/" + sub.lstrip("/")
        try:
            js2 = s.get(u2, timeout=40).text
        except Exception:
            continue
        for pat in (r"web-bff", r"token", r"Authorization", r"recaptcha"):
            for m in list(re.finditer(pat, js2))[:5]:
                print(f"  SUB {sub} HIT[{pat}]: {js2[max(0, m.start() - 200):m.end() + 200]!r}")

r = requests.get("https://www.anbima.com.br/pt_br/informar/taxas-de-cri-e-cra.htm", headers={"User-Agent": UA}, timeout=30)
for m in re.finditer(r'(?:href|src|action|data-url)="([^"]+)"', r.text):
    u = m.group(1)
    if re.search(r"download|\.xls|\.csv|\.txt|iframe|cri|cra|CRI|CRA|merc-sec|arqs|informacoes", u) and "lumis" not in u:
        print("LINK", u)
for m in re.finditer(r"<iframe[^>]+>", r.text):
    print("IFRAME", m.group(0)[:300])
i = r.text.find("CRA")
print("TRECHO", r.text[max(0, i - 1500):i + 3000] if i >= 0 else "sem CRA")
