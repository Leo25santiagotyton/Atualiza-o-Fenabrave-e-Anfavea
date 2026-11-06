"""Sonda de vitrines de caminhões seminovos (Vamos, Volvo, SelecTrucks, VolksConfia): páginas, APIs e preços."""
import re
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
      "Accept-Language": "pt-BR,pt;q=0.9"}
s = requests.Session()
s.headers.update(UA)
vistos = set()


def olha(u, prof=0):
    if u in vistos or len(vistos) > 40:
        return
    vistos.add(u)
    try:
        r = s.get(u, timeout=30)
    except Exception as e:
        print("ERRO", u, str(e)[:150])
        return
    t = r.text
    tit = re.search(r"<title>(.*?)</title>", t, re.S)
    marcas = [k for k in ("__NEXT_DATA__", "__next_f", "__NUXT__", "ng-version", "wp-content", "application/ld+json", "data-reactroot") if k in t]
    print(f"\n=== {r.status_code} {r.url} | {(tit.group(1).strip() if tit else '')[:90]} | {len(t)}b | {marcas}")
    precos = re.findall(r'R\$\s?[\d.]{5,}(?:,\d{2})?', t)
    print("  precos:", len(precos), precos[:6])
    for m in sorted(set(re.findall(r'https?://[a-zA-Z0-9.-]*(?:api|graphql|backend|estoque|seminov|vitrine|search|busca)[a-zA-Z0-9./_?=&-]*', t)))[:20]:
        print("  url:", m)
    links = sorted(set(re.findall(r'href="([^"#]*(?:seminov|estoque|caminh|usado|comprar|veiculo|ofertas)[^"#]*)"', t, re.I)))
    for m in links[:25]:
        print("  link:", m)
    if prof < 1:
        for h in links[:6]:
            olha(requests.compat.urljoin(r.url, h), prof + 1)
        for js in re.findall(r'src="([^"]+\.js[^"]*)"', t)[:12]:
            try:
                j = s.get(requests.compat.urljoin(r.url, js), timeout=30).text
            except Exception:
                continue
            for m in sorted(set(re.findall(r'["\'`](https?://[a-zA-Z0-9.-]+(?:/[a-zA-Z0-9._-]+){0,4}|/api/[a-zA-Z0-9/_-]+)["\'`]', j))):
                if re.search(r"api|graphql|estoque|veicul|vehicle|stock|search|seminov", m, re.I) and "google" not in m:
                    print("  js-url:", js[-30:], m)


for u in ["https://www.vamos.com.br/", "https://www.vamos.com.br/seminovos", "https://vamosseminovos.com.br/",
          "https://www.seminovosvolvo.com.br/", "https://www.selectrucks.com.br/", "https://www.volksconfia.com.br/"]:
    olha(u)
