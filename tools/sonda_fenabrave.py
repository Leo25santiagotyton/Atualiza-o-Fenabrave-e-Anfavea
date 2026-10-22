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
achados = {}
for p in PAGES:
    url = BASE + p
    try:
        r = s.get(url, timeout=40)
    except Exception as e:
        print("ERRO", url, e)
        continue
    print("==", url, r.status_code)
    if r.status_code != 200:
        continue
    for a in BeautifulSoup(r.text, "html.parser").find_all("a", href=True):
        h = requests.compat.urljoin(url, a["href"])
        m = re.search(r"/portal/files/(\d{4})_(\d{2})_(\d+)_usados\.pdf$", h, re.I)
        if m:
            achados[h] = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
            print("  USADOS", " ".join(a.get_text(" ").split())[:60], "|", h)
for h in sorted(achados, key=achados.get)[-1:]:
    r = s.get(h, timeout=60)
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        print("#### PDF", h, len(pdf.pages), "páginas")
        for i, pg in enumerate(pdf.pages):
            if i in (1, 2):
                continue
            print(f"--- página {i + 1}")
            print((pg.extract_text() or "")[:4000])
