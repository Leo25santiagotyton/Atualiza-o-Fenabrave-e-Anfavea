"""Diagnóstico temporário: texto do PDF FENABRAVE."""
import io, sys
sys.path.insert(0, ".")
import requests, pdfplumber
from monitor import BROWSER_HEADERS

s = requests.Session()
s.headers.update(BROWSER_HEADERS)
url = "https://www.fenabrave.org.br/portal/files/2026_09_02.pdf"
r = s.get(url, timeout=60)
print(url, r.status_code, len(r.content))
with pdfplumber.open(io.BytesIO(r.content)) as pdf:
    print("PAGES", len(pdf.pages))
    for i, p in enumerate(pdf.pages[:5]):
        print(f"----- PAGE {i+1}")
        print((p.extract_text() or "")[:4000])
