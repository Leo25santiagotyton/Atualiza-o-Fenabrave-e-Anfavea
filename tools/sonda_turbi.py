"""Sonda temporária: estrutura do Informativo FENABRAVE (caminhões por marca e modelo) e PDFs antigos disponíveis."""
import io
import re
import sys
from pathlib import Path

import pdfplumber
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from relatorios_setor import FENABRAVE_HOME, FENABRAVE_PAGE, session  # noqa: E402

Path("sonda_out").mkdir(exist_ok=True)
s = session()
try:
    s.get(FENABRAVE_HOME, timeout=30)
except Exception as e:
    print("home", e)
r = s.get(FENABRAVE_PAGE, timeout=40)
print("page", r.status_code, len(r.text))
links = []
for a in BeautifulSoup(r.text, "html.parser").find_all("a", href=True):
    h = a["href"].strip()
    if ".pdf" in h.lower():
        links.append((h, " ".join(a.get_text(" ").split())[:80]))
print("NLINKS", len(links))
for h, t in links:
    print("LINK", h, "|", t)
# outros formatos de página (ano anterior etc.)
for m in re.finditer(r'href="([^"]*(?:ano|Ano|emplacamento)[^"]*)"', r.text):
    print("HREF", m.group(1))
pdfs = sorted({requests.compat.urljoin(FENABRAVE_PAGE, h) for h, _ in links if re.search(r"/portal/files/\d{4}_\d{2}", h)})
url = pdfs[-1]
print("URL", url)
pdf = pdfplumber.open(io.BytesIO(s.get(url, timeout=90).content))
print("NPAGES", len(pdf.pages))
for i, p in enumerate(pdf.pages):
    t = p.extract_text() or ""
    head = " ".join(t.split("\n")[:3])[:200]
    print(f"PAGE {i + 1}: {head}")
for i, p in enumerate(pdf.pages):
    t = p.extract_text() or ""
    if re.search(r"caminh", t, re.I) and re.search(r"marca|modelo|fabricante", t, re.I):
        print(f"===== FULL PAGE {i + 1} =====")
        print(t[:6000])
# testa um PDF antigo (ano anterior) por URL inferida
for h in pdfs[:3]:
    try:
        rr = s.get(h, timeout=60)
        print("OLD", h, rr.status_code, len(rr.content))
    except Exception as e:
        print("OLD", h, e)
