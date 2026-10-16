"""Sonda das vitrines de seminovos (Movida e Localiza), 2ª rodada: estrutura dos dados.
Uso: python tools/sonda_seminovos.py"""
import re, json
import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
     "Accept": "text/html,application/json;q=0.9,*/*;q=0.8", "Accept-Language": "pt-BR,pt;q=0.9"}


def nd(u):
    r = requests.get(u, headers=H, timeout=40)
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    return r, (json.loads(m.group(1)) if m else None)


def resumo(o, d=0, k=""):
    if d > 3: return
    if isinstance(o, dict):
        print("  " * d + f"{k} dict[{len(o)}]: {list(o)[:25]}")
        for kk, v in list(o.items())[:25]:
            if isinstance(v, (dict, list)): resumo(v, d + 1, kk)
    elif isinstance(o, list):
        print("  " * d + f"{k} list[{len(o)}]")
        if o and isinstance(o[0], (dict, list)): resumo(o[0], d + 1, k + "[0]")


print("##### LOCALIZA")
for u in ["https://seminovos.localiza.com/carros", "https://seminovos.localiza.com/carros?page=2", "https://seminovos.localiza.com/carros/sedan",
          "https://seminovos.localiza.com/carros?carroceria=sedan"]:
    try:
        r, d = nd(u)
    except Exception as e:
        print("ERRO", u, e); continue
    pp = (d or {}).get("props", {}).get("pageProps", {})
    print(f"\n=== {u} -> {r.status_code} {r.url}")
    if u.endswith("/carros"):
        resumo(pp.get("search"), 0, "search"); resumo(pp.get("products"), 0, "products")
        prods = pp.get("products")
        lst = prods if isinstance(prods, list) else next((v for v in (prods or {}).values() if isinstance(v, list)), [])
        if lst: print("ITEM0:", json.dumps(lst[0], ensure_ascii=False)[:2500])
        print("SEARCH:", json.dumps(pp.get("search"), ensure_ascii=False)[:2500])
        print("META:", json.dumps(pp.get("_metadados"), ensure_ascii=False)[:800])
        apis = sorted(set(re.findall(r'https?://[A-Za-z0-9.\-]*localiza[A-Za-z0-9.\-]*/[A-Za-z0-9_\-./]*', r.text)))[:40]
        print("HOSTS:", apis)
    else:
        prods = pp.get("products")
        lst = prods if isinstance(prods, list) else next((v for v in (prods or {}).values() if isinstance(v, list)), [])
        print("n itens:", len(lst), "primeiro:", json.dumps(lst[0], ensure_ascii=False)[:300] if lst else None)

print("\n##### MOVIDA")
r = requests.get("https://www.seminovosmovida.com.br/", headers=H, timeout=40)
srcs = re.findall(r'<script[^>]+src="([^"]+)"', r.text)
print("scripts:", srcs[:30])
print("inline config:", re.findall(r'(?:apiUrl|API_URL|baseUrl|environment)[^,;]{0,200}', r.text)[:10])
for s in srcs[:12]:
    u = s if s.startswith("http") else "https://www.seminovosmovida.com.br/" + s.lstrip("/")
    try:
        t = requests.get(u, headers=H, timeout=40).text
    except Exception as e:
        print("ERRO", u, e); continue
    hs = sorted(set(re.findall(r'https?://[A-Za-z0-9.\-]+(?:/[A-Za-z0-9_\-./{}]*)?', t)))
    hs = [h for h in hs if not re.search(r"w3\.org|google|gstatic|facebook|schema\.org|github|mozilla|reactjs|npmjs", h)]
    print(f"\n--- {u} {len(t)}B")
    for h in hs[:60]: print("   ", h)
    for m in sorted(set(re.findall(r'["\'`](/?(?:api|v1|v2)/[A-Za-z0-9_\-./{}]{3,80})', t)))[:60]: print("    path", m)
