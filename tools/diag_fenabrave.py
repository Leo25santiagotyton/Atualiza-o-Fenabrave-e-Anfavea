"""Diagnóstico temporário: texto e tabelas dos PDFs FENABRAVE e Carta ANFAVEA."""
import io, sys
sys.path.insert(0, ".")
import requests, pdfplumber
from monitor import BROWSER_HEADERS

s = requests.Session()
s.headers.update(BROWSER_HEADERS)
for url, pages in [("https://www.fenabrave.org.br/portal/files/2026_09_02.pdf", 6),
                   ("https://www.anfavea.com.br/cartas/carta484.pdf", 8)]:
    print("=" * 100)
    r = s.get(url, timeout=60)
    print(url, r.status_code, len(r.content))
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        print("PAGES", len(pdf.pages))
        for i, p in enumerate(pdf.pages[:pages]):
            print(f"----- PAGE {i+1}")
            print((p.extract_text() or "")[:3500])
