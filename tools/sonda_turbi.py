"""Sonda temporária: ANFIR anuário/informativo — há ranking por fabricante?"""
import io
import re
import sys
from pathlib import Path

import pdfplumber
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from monitor import BROWSER_HEADERS  # noqa: E402

s = requests.Session()
s.headers.update(BROWSER_HEADERS)
pdfs = []
for url in ["https://anfir.org.br/anuario.php", "https://anfir.org.br/informativo.php", "https://anfir.org.br/sala-de-imprensa.php",
            "https://anfir.org.br/relacao-de-associados.php"]:
    try:
        r = s.get(url, timeout=40)
    except Exception as e:  # noqa: BLE001
        print("ERRO", url, e)
        continue
    print("==", url, r.status_code, len(r.text))
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
        h = requests.compat.urljoin(r.url, a["href"])
        t = " ".join(a.get_text(" ").split())[:100]
        if re.search(r"\.pdf|anuario|informativo|issuu|flip|ranking", h + " " + t, re.I):
            print("  ", t, "|", h)
            if h.lower().endswith(".pdf"):
                pdfs.append(h)
    txt = " ".join(soup.get_text(" ").split())
    for kw in ("Randon", "RANDON", "Librelato", "ranking", "Ranking", "fabricante"):
        for m in list(re.finditer(kw, txt))[:2]:
            print("  ..", txt[max(0, m.start() - 200): m.start() + 300])
seen = set()
for u in pdfs:
    if u in seen or len(seen) >= 8:
        continue
    seen.add(u)
    try:
        r = s.get(u, timeout=90)
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            print("#### PDF", u, len(pdf.pages), "páginas")
            for i, pg in enumerate(pdf.pages[:80]):
                t = pg.extract_text() or ""
                if re.search(r"RANDON|LIBRELATO|FACCHINI|GUERRA|NOMA", t, re.I):
                    print(f"--- p{i + 1}")
                    print(t[:2500])
    except Exception as e:  # noqa: BLE001
        print("ERRO PDF", u, e)
