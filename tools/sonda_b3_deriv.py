"""Sonda: cotações de DOL e FRC na B3 (API da página de derivativos) e ajustes do pregão."""

import re
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
s = requests.Session()
s.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*",
                  "Referer": "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/cotacoes/mercado-de-derivativos/"})
for sym in ("DOL", "FRC", "DDI"):
    for u in (f"https://cotacao.b3.com.br/mds/api/v1/DerivativeQuotation/{sym}",
              f"https://cotacao.b3.com.br/mds/api/v1/derivativequotation/{sym}"):
        try:
            r = s.get(u, timeout=30)
            print("API", r.status_code, u, r.headers.get("content-type"), r.text[:1500].replace("\n", " "))
            break
        except Exception as e:
            print("API ERRO", u, e)

d = date.today() - timedelta(days=1)
while d.weekday() >= 5:
    d -= timedelta(days=1)
u = "https://www2.bmf.com.br/pages/portal/bmfbovespa/lumis/lum-ajustes-do-pregao-ptBR.asp"
for how in ("get", "post"):
    try:
        r = s.get(u, params={"dData1": d.strftime("%d/%m/%Y")}, timeout=40) if how == "get" else s.post(u, data={"dData1": d.strftime("%d/%m/%Y")}, timeout=40)
        soup = BeautifulSoup(r.content, "html.parser")
        rows = []
        for tr in soup.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
            if cells:
                rows.append(cells)
        print("AJUSTES", how, r.status_code, len(r.content), "linhas", len(rows))
        cur = None
        for c in rows:
            if c[0] and not re.fullmatch(r"[FGHJKMNQUVXZ]\d{2}", c[0]):
                cur = c[0]
            if cur and re.search(r"DOL|FRC|DDI", cur):
                print("   ", c[:6])
    except Exception as e:
        print("AJUSTES ERRO", how, e)
