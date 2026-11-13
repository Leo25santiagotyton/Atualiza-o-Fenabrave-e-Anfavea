"""Sonda temporária: materiais de RI da Randoncorp (release/teaser/apresentação) e market share de semirreboques."""
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
for url in ["https://ri.randoncorp.com/", "https://ri.randoncorp.com/informacoes-financeiras/central-de-resultados/",
            "https://ri.randoncorp.com/central-de-resultados/", "https://ri.randoncorp.com/en/financial-information/results-center/"]:
    try:
        r = s.get(url, timeout=40)
    except Exception as e:  # noqa: BLE001
        print("ERRO", url, e)
        continue
    print("==", url, r.status_code, len(r.text), r.url)
    for a in BeautifulSoup(r.text, "html.parser").find_all("a", href=True):
        h = requests.compat.urljoin(r.url, a["href"])
        t = " ".join(a.get_text(" ").split())[:90]
        if re.search(r"mziq|\.pdf|release|teaser|apresenta|resultado|central", h + " " + t, re.I):
            print("  ", t, "|", h)
            if "mziq" in h or h.lower().endswith(".pdf"):
                pdfs.append((t, h))
seen = set()
for t, u in pdfs:
    if u in seen or len(seen) >= 10:
        continue
    seen.add(u)
    try:
        r = s.get(u, timeout=90)
        if b"%PDF" not in r.content[:1024]:
            print("NAO-PDF", u, r.status_code, r.headers.get("content-type"))
            continue
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            print("#### PDF", t, u, len(pdf.pages), "páginas")
            for i, pg in enumerate(pdf.pages[:60]):
                tx = pg.extract_text() or ""
                for m in re.finditer(r"(market share|participa[çc][ãa]o de mercado|share de mercado|Market Share)", tx, re.I):
                    print(f"  p{i + 1}:", " ".join(tx[max(0, m.start() - 500): m.start() + 600].split()))
    except Exception as e:  # noqa: BLE001
        print("ERRO PDF", u, e)
