"""Sonda das vitrines de seminovos (Movida e Localiza): status, tamanho, pistas de API e de __NEXT_DATA__.
Uso: python tools/sonda_seminovos.py [url ...]"""
import re, sys, json
import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
     "Accept": "text/html,application/json;q=0.9,*/*;q=0.8", "Accept-Language": "pt-BR,pt;q=0.9"}
URLS = sys.argv[1:] or [
    "https://www.seminovosmovida.com.br/", "https://seminovos.movida.com.br/", "https://www.movida.com.br/seminovos",
    "https://www.seminovos.movida.com.br/", "https://seminovos.localiza.com/", "https://seminovos.localiza.com/carros",
    "https://www.localiza.com/seminovos", "https://seminovos.localiza.com/api/veiculos", "https://www.seminovosmovida.com.br/carros",
]
for u in URLS:
    try:
        r = requests.get(u, headers=H, timeout=30, allow_redirects=True)
    except Exception as e:
        print(f"ERRO {u}: {e}"); continue
    t = r.text
    print(f"\n=== {u} -> {r.status_code} {r.url} {len(t)}B {r.headers.get('content-type')} server={r.headers.get('server')}")
    print("titulo:", (re.search(r"<title>(.*?)</title>", t, re.S) or [None, ""])[1][:120])
    if "__NEXT_DATA__" in t:
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', t, re.S)
        if m:
            try:
                d = json.loads(m.group(1)); print("NEXT_DATA chaves:", list(d.get("props", {}).get("pageProps", {}))[:30], "buildId", d.get("buildId"))
            except Exception as e: print("NEXT_DATA inválido", e)
    apis = sorted(set(re.findall(r'https?://[A-Za-z0-9.\-]+(?:/[A-Za-z0-9_\-./]*)?(?:api|graphql|search|busca|veicul|vitrine|estoque)[A-Za-z0-9_\-./?=&]*', t, re.I)))[:40]
    for a in apis: print("  api?", a)
    rel = sorted(set(re.findall(r'["\'](/(?:api|_next/data|graphql)[^"\']{0,120})', t)))[:20]
    for a in rel: print("  rel", a)
    print("  preços no html:", len(re.findall(r"R\$\s?\d{2,3}\.\d{3}", t)), "| captcha/cloudflare:", bool(re.search(r"captcha|cf-chl|challenge-platform|akamai", t, re.I)))
    print("  trecho:", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))[:300])
