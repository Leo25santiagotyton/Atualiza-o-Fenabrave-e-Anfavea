"""Sonda temporária: onde a FENABRAVE publica o mercado de usados e seminovos (transferências)."""
import io
import re

import pdfplumber
import requests
from bs4 import BeautifulSoup

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from monitor import BROWSER_HEADERS  # noqa: E402

s = requests.Session()
s.headers.update(BROWSER_HEADERS)
BASE = "https://www.fenabrave.org.br/portalv2/"
PAGES = ["home/imprensa", "Conteudo/emplacamentos", "Conteudo/seminovos-e-usados", "Conteudo/seminovoseusados",
         "Conteudo/usados", "Conteudo/seminovos", "Conteudo/transferencias", "Conteudo/dados-de-mercado", "home"]
for ano, mes in [(a, m) for a in (2025, 2026) for m in range(1, 13) if (a, m) >= (2025, 6) and (a, m) <= (2026, 10)]:
    for n in (1, 2, 3, 4):
        h = f"https://www.fenabrave.org.br/portal/files/{ano}_{mes:02d}_{n}_usados.pdf"
        try:
            r = s.get(h, timeout=40)
        except Exception as e:
            print("ERRO", h, e)
            continue
        ok = r.status_code == 200 and r.content[:4] == b"%PDF"
        print(h, r.status_code, len(r.content), "PDF" if ok else "")
        if ok:
            with pdfplumber.open(io.BytesIO(r.content)) as pdf:
                print((pdf.pages[0].extract_text() or "")[:600].replace("\n", " | "))
