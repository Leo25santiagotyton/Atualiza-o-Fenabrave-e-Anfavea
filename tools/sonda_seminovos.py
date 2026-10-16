"""Sonda da vitrine de seminovos da Movida, 4ª rodada: rotas elasticsearch do main.js e testes.
Uso: python tools/sonda_seminovos.py"""
import re, json
import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
     "Accept": "application/json, text/plain, */*", "Accept-Language": "pt-BR,pt;q=0.9",
     "Origin": "https://www.seminovosmovida.com.br", "Referer": "https://www.seminovosmovida.com.br/"}
r = requests.get("https://www.seminovosmovida.com.br/", headers={**H, "Accept": "text/html"}, timeout=40)
main = next(s for s in re.findall(r'<script[^>]+src="([^"]+)"', r.text) if s.startswith("main."))
t = requests.get("https://www.seminovosmovida.com.br/" + main, headers=H, timeout=60).text
seen = set()
for m in re.finditer(r"elasticsearch", t):
    c = t[max(0, m.start() - 250):m.end() + 350].replace("\n", " ")
    k = t[m.start():m.start() + 60]
    if k in seen: continue
    seen.add(k); print("ctx", c, "\n")
B = "https://be-seminovos.movidacloud.com.br"
for p, meth, body in [("/elasticsearch/veiculos", "GET", None), ("/elasticsearch/veiculos", "POST", {}), ("/elasticsearch/veiculos/busca", "POST", {}),
                      ("/elasticsearch/marcas/", "GET", None), ("/elasticsearch/veiculos/autocomplete?query=onix", "GET", None),
                      ("/elasticsearch/veiculos/filtros", "GET", None), ("/elasticsearch/veiculos?page=1", "GET", None)]:
    try:
        rr = requests.request(meth, B + p, headers=H, json=body, timeout=30)
        print(f"  {meth} {p} -> {rr.status_code} {rr.headers.get('content-type')} {rr.text[:600]!r}")
    except Exception as e:
        print("  ERRO", p, e)
