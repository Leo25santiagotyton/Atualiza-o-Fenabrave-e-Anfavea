"""Sonda temporária: onde a FENABRAVE publica o mercado de usados e seminovos (transferências)."""
import io
import re

import pdfplumber
import requests
from bs4 import BeautifulSoup

from monitor import BROWSER_HEADERS

s = requests.Session()
s.headers.update(BROWSER_HEADERS)
BASE = "https://www.fenabrave.org.br/portalv2/"
PAGES = ["home/imprensa", "Conteudo/emplacamentos", "Conteudo/seminovos-e-usados", "Conteudo/seminovoseusados",
         "Conteudo/usados", "Conteudo/seminovos", "Conteudo/transferencias", "Conteudo/dados-de-mercado", "home"]
achados = set()
for p in PAGES:
    url = BASE + p
    try:
        r = s.get(url, timeout=40)
    except Exception as e:
        print("ERRO", url, e)
        continue
    print("==", url, r.status_code, len(r.text))
    if r.status_code != 200:
        continue
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
        t = " ".join(a.get_text(" ").split())
        h = requests.compat.urljoin(url, a["href"])
        if re.search(r"usad|semin|transfer|conteudo/|\.pdf", (t + " " + h), re.I):
            print("  ", t[:80], "|", h)
            if re.search(r"usad|semin|transfer", t + h, re.I) and h.lower().endswith(".pdf"):
                achados.add(h)
for h in sorted(achados)[-3:]:
    try:
        r = s.get(h, timeout=60)
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            print("#### PDF", h, len(pdf.pages), "páginas")
            for i, pg in enumerate(pdf.pages[:3]):
                print(f"--- página {i + 1}")
                print((pg.extract_text() or "")[:3500])
    except Exception as e:
        print("ERRO PDF", h, e)
