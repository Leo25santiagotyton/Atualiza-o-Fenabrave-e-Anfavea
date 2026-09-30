"""Sonda: mostra o que a B3 devolve para o arquivo de taxas de swap (TaxaSwap)."""

import io
import zipfile
from datetime import date, timedelta

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Accept": "*/*"}
s = requests.Session()
s.headers.update(H)
d = date.today() - timedelta(days=1)
while d.weekday() >= 5:
    d -= timedelta(days=1)
urls = [
    f"https://www.b3.com.br/pesquisapregao/download?filelist=TS{d:%y%m%d}.ex_,",
    f"https://www.b3.com.br/pesquisapregao/download?filelist=TS{d:%y%m%d}.ex_",
    f"https://www.b3.com.br/pesquisapregao/download?filelist=TaxaSwap{d:%y%m%d}.ex_,",
    "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/boletins-diarios/pesquisa-por-pregao/pesquisa-por-pregao/",
    f"https://arquivos.b3.com.br/api/download/requestname?fileName=TaxaSwap&date={d:%Y-%m-%d}&recaptchaToken=",
    f"https://arquivos.b3.com.br/tabelas/table/TaxaSwap/{d:%Y-%m-%d}/1",
]
for u in urls:
    print("=" * 90)
    print(u)
    try:
        r = s.get(u, timeout=40, allow_redirects=True)
        print("status", r.status_code, "| tipo", r.headers.get("content-type"), "| bytes", len(r.content), "| final", r.url)
        print("início:", r.content[:300])
        try:
            zf = zipfile.ZipFile(io.BytesIO(r.content))
            print("ZIP:", zf.namelist())
            for n in zf.namelist():
                inner = zf.read(n)
                print("  ", n, len(inner), inner[:120])
                try:
                    z2 = zipfile.ZipFile(io.BytesIO(inner))
                    print("   ZIP interno:", z2.namelist())
                    for n2 in z2.namelist():
                        print("   ", n2, z2.read(n2)[:600].decode("latin-1"))
                except zipfile.BadZipFile:
                    pass
        except zipfile.BadZipFile:
            pass
    except Exception as e:
        print("ERRO", e)
