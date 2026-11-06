"""Sonda de caminhões seminovos: estrutura de dados da Vamos, SelecTrucks e VolksConfia."""
import json
import re
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
      "Accept-Language": "pt-BR,pt;q=0.9"}
s = requests.Session()
s.headers.update(UA)


def flight(t):
    return "".join(json.loads('"' + m + '"') for m in re.findall(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', t))


print("##### VAMOS")
t = s.get("https://vamos.com.br/seminovos", timeout=40).text
f = flight(t)
for k in ['"price"', '"preco"', '"total"', '"totalPages"', '"page"', '"category"', '"categoria"', '"tipo"', '"km"', '"quilometragem"']:
    i = f.find(k)
    print(k, f.count(k), repr(f[max(0, i - 400):i + 300]) if i >= 0 else "")
for q in ["?page=2", "?pagina=2", "?p=2", "/caminhoes", "?tipo=caminhao", "?categoria=caminhao"]:
    try:
        r2 = s.get("https://vamos.com.br/seminovos" + q, timeout=40)
        ids = re.findall(r'/seminovo/([a-z0-9-]+)', r2.text)
        print("Q", q, r2.status_code, len(set(ids)), list(dict.fromkeys(ids))[:2])
    except Exception as e:
        print("Q", q, e)
print("ids pag1", len(set(re.findall(r'/seminovo/([a-z0-9-]+)', t))))
m = re.search(r'(\d[\d.]*)\s*(?:ve[ií]culos|seminovos|resultados|an[uú]ncios)', re.sub(r"<[^>]+>", " ", t))
print("contagem:", m.group(0) if m else None)

print("\n##### SELECTRUCKS")
t = s.get("https://www.selectrucks.com.br/caminhao-seminovos-usados/concessionaria-selectrucks", timeout=40).text
for k in ["vehicles/integrator/filter", "duda_id", "integrator", "motorleads"]:
    for mm in list(re.finditer(re.escape(k), t))[:3]:
        print(k, repr(t[max(0, mm.start() - 300):mm.start() + 300]))
        print("--")

print("\n##### VOLKSCONFIA")
t = s.get("https://www.volksconfia.com.br/", timeout=40).text
for js in re.findall(r'src="([^"]+\.js)"', t):
    j = s.get(requests.compat.urljoin("https://www.volksconfia.com.br/", js), timeout=40).text
    for mm in list(re.finditer(r'api\.volksconfia\.com\.br', j))[:3]:
        print("ctx", repr(j[max(0, mm.start() - 200):mm.start() + 200]))
    paths = sorted(set(re.findall(r'["\'`](/(?:v\d/)?[a-zA-Z_-]*(?:vehicle|veicul|estoque|stock|search|ofert|seminov|anunc|produto|caminh)[a-zA-Z0-9/_-]*)["\'`]', j, re.I)))
    print("paths", paths[:40])
