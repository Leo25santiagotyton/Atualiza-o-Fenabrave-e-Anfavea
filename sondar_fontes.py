"""Sonda temporária: mostra o formato das fontes de negócios (SND) e de CRI/CRA (ANBIMA).
Usada só para escrever os leitores; pode ser apagada depois."""

import re
from datetime import datetime, timedelta

import requests

from alerta_acoes import BRT, HEADERS

d = datetime.now(BRT).date() - timedelta(days=1)
while d.weekday() >= 5:
    d -= timedelta(days=1)
dt = d.strftime("%d/%m/%Y")

URLS = [
    f"https://www.debentures.com.br/exploreosnd/consultaadados/mercadosecundario/precosdenegociacao_e.asp?op_exc=False&emissor=&ativo=&dt_ini={dt}&dt_fim={dt}",
    f"https://www.debentures.com.br/exploreosnd/consultaadados/mercadosecundario/precosdenegociacao_r.asp?op_exc=False&emissor=&ativo=VAMO33&dt_ini={dt}&dt_fim={dt}",
    "https://www.anbima.com.br/pt_br/informar/precos-e-indices/precos/taxas-de-cri-e-cra.htm",
    "https://www.anbima.com.br/informacoes/cri-cra/",
    f"https://www.anbima.com.br/informacoes/cri-cra/arqs/cri{d:%y%m%d}.txt",
    f"https://www.anbima.com.br/informacoes/cri-cra/arqs/cra{d:%y%m%d}.txt",
]

s = requests.Session()
s.headers.update({**HEADERS, "Accept": "*/*"})
for u in URLS:
    print("=" * 100)
    print(u)
    try:
        r = s.get(u, timeout=30)
        text = r.content.decode("latin-1", "replace")
        print("status", r.status_code, "| tipo", r.headers.get("content-type"), "| bytes", len(r.content))
        print(text[:1500])
        links = sorted(set(re.findall(r'href="([^"]*(?:cri|cra|CRI|CRA|\.xls|\.csv|\.txt|arqs)[^"]*)"', text)))
        if links:
            print("LINKS:", links[:40])
    except Exception as e:
        print("ERRO", e)
