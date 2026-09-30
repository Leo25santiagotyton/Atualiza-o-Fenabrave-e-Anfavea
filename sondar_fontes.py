"""Sonda temporária: características das emissões no SND (lista completa de papéis),
hub de dados da B3 (curva DI) e API do portal de CRI/CRA da ANBIMA."""

import re
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from alerta_acoes import BRT, HEADERS

s = requests.Session()
s.headers.update({**HEADERS, "Accept": "*/*"})
d = datetime.now(BRT).date() - timedelta(days=1)
while d.weekday() >= 5:
    d -= timedelta(days=1)


def show(u, rows=25, raw=False):
    print("=" * 100)
    print("GET", u)
    try:
        r = s.get(u, timeout=40)
        print("status", r.status_code, "| tipo", r.headers.get("content-type"), "| bytes", len(r.content))
        if raw or "json" in (r.headers.get("content-type") or "") or "javascript" in (r.headers.get("content-type") or ""):
            print(r.text[:1500])
            return r
        soup = BeautifulSoup(r.content, "html.parser")
        n = 0
        for tr in soup.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            cells = [c for c in cells if c]
            if len(cells) >= 3:
                print(" | ".join(cells)[:400])
                n += 1
                if n >= rows:
                    break
        if not n:
            print("TEXTO:", soup.get_text(" ", strip=True)[:600])
        print("SCRIPTS:", [x.get("src") for x in soup.find_all("script") if x.get("src")][:10])
        return r
    except Exception as e:
        print("ERRO", e)


# lista de emissões/papéis por emissor no SND
show("https://www.debentures.com.br/exploreosnd/consultaadados/emissoesdedebentures/caracteristicas_r.asp?tip_deb=publicas&op_exc=False&ativo=VAMO19")
show("https://www.debentures.com.br/exploreosnd/consultaadados/emissoesdedebentures/caracteristicas_r.asp?tip_deb=publicas&op_exc=False&emissor=VAMOS")
show("https://www.debentures.com.br/exploreosnd/consultaadados/emissoesdedebentures/puhistorico_r.asp?op_exc=False&ativo=VAMO19&dt_ini=01/09/2026&dt_fim=29/09/2026")
# hub de dados da B3: taxas de mercado para swaps (curva DI x Pré)
show("https://sistemaswebb3-derivativos.b3.com.br/referenceRatesPage/all?language=pt-br", raw=True)
show(f"https://sistemaswebb3-derivativos.b3.com.br/referenceRatesProxy/Search/GetDownloadFile/{d:%Y-%m-%d}/PRE", raw=True)
show(f"https://arquivos.b3.com.br/tabelas/TaxaSwap/{d:%Y-%m-%d}?lang=pt", raw=True)
# portal de CRI/CRA da ANBIMA: procura a API nos scripts
r = show("https://data.anbima.com.br/certificado-de-recebiveis", raw=True)
if r is not None:
    for src in re.findall(r'src="([^"]+\.js)"', r.text)[:6]:
        url = src if src.startswith("http") else "https://data.anbima.com.br" + (src if src.startswith("/") else "/" + src)
        try:
            js = s.get(url, timeout=40).text
            apis = sorted(set(re.findall(r'["\'`](https?://[^"\'`]*api[^"\'`]*|/api/[^"\'`]{3,80})["\'`]', js)))
            print("JS", url, len(js), "APIs:", apis[:30])
        except Exception as e:
            print("JS ERRO", url, e)
