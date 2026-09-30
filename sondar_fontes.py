"""Sonda temporária: mostra o formato das fontes de negócios (SND), da curva DI x Pré
e de CRI/CRA. Usada só para escrever os leitores; pode ser apagada depois."""

import re
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from alerta_acoes import BRT, HEADERS

d = datetime.now(BRT).date() - timedelta(days=1)
while d.weekday() >= 5:
    d -= timedelta(days=1)
dt = d.strftime("%d/%m/%Y")
d7 = (d - timedelta(days=7)).strftime("%d/%m/%Y")

s = requests.Session()
s.headers.update({**HEADERS, "Accept": "*/*"})


def show(u, method="get", data=None, rows=40):
    print("=" * 100)
    print(method.upper(), u, data or "")
    try:
        r = s.post(u, data=data, timeout=30) if method == "post" else s.get(u, timeout=30)
        print("status", r.status_code, "| tipo", r.headers.get("content-type"), "| bytes", len(r.content))
        if "json" in (r.headers.get("content-type") or ""):
            print(r.text[:2000])
            return
        soup = BeautifulSoup(r.content, "html.parser")
        n = 0
        for tr in soup.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) >= 3 and any(re.search(r"\d", c) for c in cells):
                print(" | ".join(cells)[:300])
                n += 1
                if n >= rows:
                    break
        if not n:
            txt = soup.get_text(" ", strip=True)
            print("SEM LINHAS DE TABELA. Texto:", txt[:800])
            print("IFRAMES/FORMS:", [f.get("src") for f in soup.find_all("iframe")], [(f.get("action"), f.get("method")) for f in soup.find_all("form")])
    except Exception as e:
        print("ERRO", e)


# negócios do SND para um papel (5 dias)
show(f"https://www.debentures.com.br/exploreosnd/consultaadados/mercadosecundario/precosdenegociacao_r.asp?op_exc=False&emissor=&ativo=VAMO33&dt_ini={d7}&dt_fim={dt}")
show(f"https://www.debentures.com.br/exploreosnd/consultaadados/mercadosecundario/precosdenegociacao_r.asp?op_exc=False&emissor=&ativo=&dt_ini={dt}&dt_fim={dt}", rows=15)
# curva DI x Pré (B3)
show(f"https://www2.bmf.com.br/pages/portal/bmfbovespa/lumis/lum-taxas-referenciais-bmf-ptBR.asp?Data={dt}&Data1={d:%Y%m%d}&slcTaxa=PRE", rows=10)
show("https://www2.bmf.com.br/pages/portal/bmfbovespa/lumis/lum-taxas-referenciais-bmf-ptBR.asp", "post",
     {"Data": dt, "Data1": f"{d:%Y%m%d}", "slcTaxa": "PRE"}, rows=10)
# ETTJ da ANBIMA (alternativa para a curva)
show("https://www.anbima.com.br/informacoes/est-termo/CZ-down.asp", "post",
     {"Idioma": "PT", "Dt_Ref": dt, "saida": "csv"}, rows=10)
# CRI/CRA no portal de dados da ANBIMA
for u in ["https://data.anbima.com.br/certificado-de-recebiveis",
          "https://data.anbima.com.br/api/v1/certificado-de-recebiveis/precos?page=0&size=5",
          "https://www.anbima.com.br/pt_br/informar/precos-e-indices/precos/cri-e-cra.htm"]:
    show(u, rows=10)
