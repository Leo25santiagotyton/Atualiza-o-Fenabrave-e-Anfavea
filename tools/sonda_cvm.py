"""Sonda temporária: notícia B3/Trillia de financiamentos e taxa diária de veículos."""
import re, requests
from bs4 import BeautifulSoup
H = {"User-Agent": "curl/8.5.0"}
u = "https://www.b3.com.br/pt_br/noticias/financiamento-de-veiculos-bate-recorde-para-agosto-e-alcanca-maior-volume-em-15-anos-aponta-trillia.htm"
r = requests.get(u, headers=H, timeout=60); print(r.status_code)
s = BeautifulSoup(r.text, "html.parser")
t = (s.find("article") or s.find("main") or s).get_text("\n", strip=True)
i = t.find("Trillia"); print(t[max(0, i - 300):i + 4500])
for a in s.find_all("a", href=True):
    if re.search(r"\.pdf|xlsx|data/files", a["href"], re.I): print("LINK", a.get_text(" ", strip=True)[:60], a["href"])
r = requests.get("https://www.b3.com.br/pt_br/noticias/", headers=H, timeout=60)
for m in sorted(set(re.findall(r'href="([^"]*noticias/[^"]+\.htm)"', r.text))): print("NOT", m)
base = "https://olinda.bcb.gov.br/olinda/servico/taxaJuros/versao/v2/odata/"
r = requests.get(base + "TaxasJurosDiariaPorInicioPeriodo", headers=H, timeout=90, params={
    "$format": "json", "$top": "400", "$orderby": "InicioPeriodo desc",
    "$filter": "Modalidade eq 'Aquisição de veículos - Prefixado'"})
v = r.json().get("value", []); print("VEIC", r.status_code, len(v)); print(v[:3])
print(sorted({(x["InicioPeriodo"], x["FimPeriodo"]) for x in v})[-12:])
for n in [20645, 21121, 21096, 20886, 20864]:
    r = requests.get(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{n}/dados/ultimos/2?formato=json", headers=H, timeout=60)
    print("SGS", n, r.text[:140])
