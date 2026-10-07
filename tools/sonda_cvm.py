"""Sonda temporária: notícia B3/Trillia de financiamentos e taxa diária de veículos."""
import re, requests, traceback
from bs4 import BeautifulSoup
HB = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Accept-Language": "pt-BR,pt;q=0.9", "Accept": "text/html,application/xhtml+xml"}
H = {"User-Agent": "curl/8.5.0"}
def tenta(f):
    try: f()
    except Exception: traceback.print_exc()
def b3():
    u = "https://www.b3.com.br/pt_br/noticias/financiamento-de-veiculos-bate-recorde-para-agosto-e-alcanca-maior-volume-em-15-anos-aponta-trillia.htm"
    for h in (HB, H):
        r = requests.get(u, headers=h, timeout=60); print("B3", r.status_code)
        if r.status_code == 200: break
    s = BeautifulSoup(r.text, "html.parser")
    t = s.get_text("\n", strip=True)
    i = t.find("financiad"); print(t[max(0, i - 600):i + 4500])
    for a in s.find_all("a", href=True):
        if re.search(r"\.pdf|xlsx|data/files", a["href"], re.I): print("LINK", a.get_text(" ", strip=True)[:60], a["href"])
def diaria():
    base = "https://olinda.bcb.gov.br/olinda/servico/taxaJuros/versao/v2/odata/"
    r = requests.get(base + "TaxasJurosDiariaPorInicioPeriodo?$format=json&$top=400&$orderby=InicioPeriodo%20desc&$filter=Modalidade%20eq%20'Aquisi%C3%A7%C3%A3o%20de%20ve%C3%ADculos%20-%20Prefixado'", headers=H, timeout=90)
    print("VEIC", r.status_code, r.text[:200] if r.status_code != 200 else "")
    v = r.json().get("value", []); print(len(v)); print(v[:2])
    print(sorted({(x["InicioPeriodo"], x["FimPeriodo"]) for x in v})[-12:])
def sgs():
    for n in [20645, 21121, 21096, 20886, 20864]:
        r = requests.get(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{n}/dados/ultimos/2?formato=json", headers=H, timeout=60)
        print("SGS", n, r.text[:140])
for f in (diaria, sgs, b3): tenta(f)
