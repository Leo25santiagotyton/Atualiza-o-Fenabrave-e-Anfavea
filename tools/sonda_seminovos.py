"""Sonda das vitrines de seminovos (Movida e Localiza), 3ª rodada: endpoints de busca e paginação.
Uso: python tools/sonda_seminovos.py"""
import re, json
import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
     "Accept": "application/json, text/plain, */*", "Accept-Language": "pt-BR,pt;q=0.9",
     "Origin": "https://www.seminovosmovida.com.br", "Referer": "https://www.seminovosmovida.com.br/"}


def nd(u):
    r = requests.get(u, headers={**H, "Accept": "text/html"}, timeout=40)
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    return r, (json.loads(m.group(1)) if m else None)


print("##### LOCALIZA paginação")
for u in ["https://seminovos.localiza.com/carros?registrosPorPagina=100", "https://seminovos.localiza.com/carros?RegistrosPorPagina=100&page=3",
          "https://seminovos.localiza.com/carros?categorias=suv", "https://seminovos.localiza.com/carros?categorias=hatch&page=2"]:
    try:
        r, d = nd(u)
        pp = (d or {}).get("props", {}).get("pageProps", {})
        lst = pp.get("products") or []
        print(u, r.status_code, "itens", len(lst), "meta", json.dumps(pp.get("_metadados", {}), ensure_ascii=False)[:200],
              "cats", sorted({x.get("categoriaDescricao") for x in lst}))
    except Exception as e:
        print("ERRO", u, e)
for u in ["https://seminovos.localiza.com/_next/data/version-4.57.0/carros.json?page=2"]:
    r = requests.get(u, headers=H, timeout=40); print(u, r.status_code, r.text[:200])

print("\n##### MOVIDA main.js")
r = requests.get("https://www.seminovosmovida.com.br/", headers={**H, "Accept": "text/html"}, timeout=40)
main = next(s for s in re.findall(r'<script[^>]+src="([^"]+)"', r.text) if s.startswith("main."))
t = requests.get("https://www.seminovosmovida.com.br/" + main, headers=H, timeout=60).text
strs = sorted(set(re.findall(r'["\'`]([A-Za-z0-9_\-]+(?:/[A-Za-z0-9_\-{}$.]+){1,5}/?)["\'`]', t)))
for s in strs:
    if re.search(r"veicul|busca|search|estoque|filtro|vitrine|oferta|categor|modelo|marca|listag|catalog", s, re.I) and not s.endswith((".webp", ".png", ".svg")):
        print("  str", s)
for m in re.finditer(r"be-seminovos|apiUrl|baseUrl|api/v1/", t):
    print("  ctx", t[max(0, m.start() - 150):m.end() + 150].replace("\n", " "))
    if m.start() > 0 and t.count("api/v1/") > 40: break

print("\n##### MOVIDA candidatos")
B = "https://be-seminovos.movidacloud.com.br/api/v1/"
for p in ["veiculo/busca", "veiculos", "veiculo", "veiculo/listar", "veiculo/filtros", "busca", "search", "veiculo/search", "estoque", "vitrine",
          "veiculo/busca?pagina=1&quantidade=20", "veiculos/busca"]:
    for meth in ("GET", "POST"):
        try:
            rr = requests.request(meth, B + p, headers=H, json={} if meth == "POST" else None, timeout=30)
            print(f"  {meth} {p} -> {rr.status_code} {rr.headers.get('content-type')} {rr.text[:220]!r}")
        except Exception as e:
            print("  ERRO", p, e)
