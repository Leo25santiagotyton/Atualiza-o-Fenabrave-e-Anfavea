"""Sonda da vitrine de seminovos da Movida, 5ª rodada: paginação da busca (POST /elasticsearch/veiculos).
Uso: python tools/sonda_seminovos.py"""
import re, json
import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
     "Accept": "application/json, text/plain, */*", "Accept-Language": "pt-BR,pt;q=0.9",
     "Origin": "https://www.seminovosmovida.com.br", "Referer": "https://www.seminovosmovida.com.br/"}
U = "https://be-seminovos.movidacloud.com.br/elasticsearch/veiculos"
r = requests.post(U, headers=H, json={}, timeout=40).json()
print("chaves:", {k: (type(v).__name__, len(v) if isinstance(v, (list, dict)) else v) for k, v in r.items()})
it = r["data"][0]
print("item chaves:", list(it))
print("item:", json.dumps({k: v for k, v in it.items() if k not in ("caracteristicas",)}, ensure_ascii=False)[:1500])
first = lambda j: [x.get("id") or x.get("placa") or x.get("codigo") for x in (j.get("data") or [])[:3]]
print("ids0", first(r), "n", len(r["data"]))
for body in [{"pagina": 2}, {"page": 2}, {"from": 50}, {"pagina": 2, "quantidade": 100}, {"size": 200}, {"page": 2, "size": 100},
             {"categoria": "SUV"}, {"categoria": ["SUV"]}, {"ordenacao": "menor_preco"}]:
    try:
        j = requests.post(U, headers=H, json=body, timeout=40).json()
        print(body, "->", "n", len(j.get("data") or []), "ids", first(j), {k: v for k, v in j.items() if k != "data"} if len(json.dumps({k: v for k, v in j.items() if k != "data"})) < 400 else "meta grande",
              "cats", sorted({x.get("categoria") for x in j.get("data") or []}))
    except Exception as e:
        print(body, "ERRO", e)
r0 = requests.get("https://www.seminovosmovida.com.br/", headers={**H, "Accept": "text/html"}, timeout=40)
main = next(s for s in re.findall(r'<script[^>]+src="([^"]+)"', r0.text) if s.startswith("main."))
t = requests.get("https://www.seminovosmovida.com.br/" + main, headers=H, timeout=60).text
for m in re.finditer(r"getSearch\(", t):
    print("call", t[max(0, m.start() - 700):m.end() + 200].replace("\n", " "), "\n")
for w in ["pagina:", "page:", "quantidade", "per_page", "pageSize", "itensPorPagina", "from:"]:
    for m in list(re.finditer(re.escape(w), t))[:3]:
        print(w, "::", t[max(0, m.start() - 200):m.end() + 200].replace("\n", " "), "\n")
