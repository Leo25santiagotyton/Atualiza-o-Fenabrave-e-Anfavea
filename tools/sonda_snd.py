"""Sonda: acha o link da ficha (características) de uma debênture no SND a partir da lista de emissões."""

import re

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
s = requests.Session()
s.headers.update({"User-Agent": UA})
BASE = "https://www.debentures.com.br/exploreosnd/consultaadados/emissoesdedebentures/"
r = s.get(BASE + "caracteristicas_r.asp?tip_deb=publicas&op_exc=False", timeout=90)
print("LISTA", r.status_code, len(r.content))
soup = BeautifulSoup(r.content, "html.parser")
for tr in soup.find_all("tr"):
    t = tr.get_text(" ", strip=True)
    if t.startswith("VAMO33") or t.startswith("VAMO34"):
        print("ROW", t[:200])
        for a in tr.find_all("a"):
            print("  A", a.get("href"), a.get("onclick"))
        print("  HTML", str(tr)[:800])
forms = soup.find_all("form")
print("FORMS", [(f.get("action"), f.get("method")) for f in forms][:5])
cands = [
    BASE + "caracteristicas_d.asp?tip_deb=publicas&selecao=VAMO33",
    BASE + "caracteristicas_d.asp?selecao=VAMO33&tip_deb=publicas&op_exc=False",
    BASE + "caracteristicas_d.asp?ativo=VAMO33",
    BASE + "caracteristicas_d.asp?tip_deb=publicas&ativo=VAMO33",
    "https://www.debentures.com.br/exploreosnd/consultaadados/emissoesdedebentures/caracteristicas_d.asp?op_exc=False&ativo=VAMO33&tip_deb=publicas",
]
for u in cands:
    try:
        x = s.get(u, timeout=60)
        txt = BeautifulSoup(x.content, "html.parser").get_text(" ", strip=True)
        print("TRY", x.status_code, len(x.content), u, "\n   ", txt[:1500])
    except Exception as e:
        print("TRY ERRO", u, e)
