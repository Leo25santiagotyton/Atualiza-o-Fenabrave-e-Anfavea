"""Sonda: ajustes de DOL e FRC na B3 (arquivo de preços da Pesquisa por Pregão e página de ajustes)."""

import io
import re
import zipfile
from datetime import date, timedelta

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
s = requests.Session()
s.headers.update({"User-Agent": UA})

d = date.today() - timedelta(days=1)
while d.weekday() >= 5:
    d -= timedelta(days=1)


def walk(blob, name="", depth=0):
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        yield name, blob
        return
    for n in zf.namelist():
        yield from walk(zf.read(n), n, depth + 1) if depth < 4 else [(n, zf.read(n))]


for pref in ("PR", "AJ", "BF", "SPRE"):
    u = f"https://www.b3.com.br/pesquisapregao/download?filelist={pref}{d:%y%m%d}.zip,"
    try:
        r = s.get(u, timeout=90)
        print("FILE", pref, r.status_code, len(r.content), r.headers.get("content-type"))
        if r.status_code != 200 or len(r.content) < 500:
            continue
        for name, data in walk(r.content):
            txt = data.decode("utf-8", "replace")
            print("  PART", name, len(data), txt[:300].replace("\n", " "))
            for sym in ("FRC", "DOL"):
                hits = [m.start() for m in re.finditer(rf"<TckrSymb>{sym}[A-Z]\d\d</TckrSymb>", txt)][:3]
                for h in hits:
                    print(f"  {sym}:", txt[max(0, h - 200):h + 1400].replace("\n", " "))
            if not any(re.search(rf"{sym}[FGHJKMNQUVXZ]\d\d", txt) for sym in ("FRC", "DOL")):
                continue
            for sym in ("FRC", "DOL"):
                m = re.search(rf"{sym}[FGHJKMNQUVXZ]\d\d", txt)
                if m:
                    print(f"  {sym} (texto):", txt[max(0, m.start() - 300):m.start() + 900].replace("\n", " "))
    except Exception as e:
        print("FILE ERRO", pref, e)

u = "https://www2.bmf.com.br/pages/portal/bmfbovespa/lumis/lum-ajustes-do-pregao-ptBR.asp"
r = s.post(u, data={"dData1": d.strftime("%d/%m/%Y")}, timeout=40)
t = r.content.decode("latin-1")
i = t.find("DOL")
print("AJUSTES", r.status_code, len(t), "pos DOL", i)
print(t[max(0, i - 1500):i + 2500] if i >= 0 else t[:3000])
for name in ("FRC", "DDI"):
    j = t.find(name)
    print("AJUSTES", name, j, t[max(0, j - 300):j + 1500] if j >= 0 else "")
