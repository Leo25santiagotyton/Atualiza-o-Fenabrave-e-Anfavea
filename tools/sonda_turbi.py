"""Sonda temporária: conteúdo do PDF da ANFIR."""
import io
import sys
from pathlib import Path

import pdfplumber
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from monitor import BROWSER_HEADERS  # noqa: E402

s = requests.Session()
s.headers.update(BROWSER_HEADERS)
for url in ["https://anfir.org.br/ADM/VIEW/ARQUIVO/ESTATISTICA/1792592316-DADOS%20IMPRENSA%20-%20JANEIRO%20A%20SETEMBRO%202026.pdf",
            "https://anfir.org.br/ADM/VIEW/ARQUIVO/ESTATISTICA/1790095737-DADOS%20IMPRENSA%20-%20JANEIRO%20A%20AGOSTO%202026.pdf"]:
    r = s.get(url, timeout=60)
    print("==", url, r.status_code, r.headers.get("content-type"), len(r.content))
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        print("pages", len(pdf.pages))
        for i, pg in enumerate(pdf.pages[:6]):
            print(f"--- page {i+1}")
            print(pg.extract_text() or "(sem texto)")
            for t in pg.extract_tables()[:3]:
                print("TABLE", t[:25])
