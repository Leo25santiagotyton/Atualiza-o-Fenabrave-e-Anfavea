"""Sonda da vitrine pública de seminovos da Turbi: acha a página de venda e a API que ela usa."""
import re
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"}
s = requests.Session()
s.headers.update(UA)
vistos = set()


def olha(u, prof=0):
    if u in vistos or len(vistos) > 25:
        return
    vistos.add(u)
    try:
        r = s.get(u, timeout=30)
    except Exception as e:
        print("ERRO", u, e)
        return
    t = r.text
    tit = re.search(r"<title>(.*?)</title>", t, re.S)
    print(f"\n=== {r.status_code} {r.url} | {tit.group(1).strip()[:100] if tit else ''} | {len(t)} bytes | next={'__NEXT_DATA__' in t} nuxt={'__NUXT__' in t}")
    for m in sorted(set(re.findall(r'https?://[a-zA-Z0-9.-]*(?:api|graphql|backend|seminov|vitrine|cms)[a-zA-Z0-9./_-]*', t)))[:30]:
        print("  url:", m)
    for m in sorted(set(re.findall(r'href="([^"]*(?:seminov|comprar|venda|carros|estoque|vitrine)[^"]*)"', t, re.I)))[:30]:
        print("  link:", m)
    for m in re.findall(r'R\$\s?[\d.]+(?:,\d{2})?', t)[:10]:
        print("  preco:", m)
    nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', t, re.S)
    if nd:
        print("  NEXT_DATA:", nd.group(1)[:1500])
    if prof < 1:
        for h in sorted(set(re.findall(r'href="([^"]*(?:seminov|comprar|venda|estoque|vitrine)[^"]*)"', t, re.I)))[:8]:
            olha(requests.compat.urljoin(r.url, h), prof + 1)
        for js in re.findall(r'src="([^"]+\.js)"', t)[:15]:
            try:
                j = s.get(requests.compat.urljoin(r.url, js), timeout=30).text
            except Exception:
                continue
            for m in sorted(set(re.findall(r'https?://[a-zA-Z0-9.-]+(?:/[a-zA-Z0-9._-]+){0,4}', j))):
                if re.search(r"api|graphql|seminov|vehicle|veicul|car", m, re.I) and "google" not in m:
                    print("  js-url:", m)


for u in ["https://turbi.com.br/", "https://www.turbi.com.br/seminovos", "https://seminovos.turbi.com.br/",
          "https://turbi.com.br/seminovos", "https://www.turbi.com.br/comprar", "https://turbi.com.br/compre"]:
    olha(u)
