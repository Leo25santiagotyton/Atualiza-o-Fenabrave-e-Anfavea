"""Sonda temporária: páginas de implementos (ranking por marca) no Informativo da FENABRAVE."""
import io
import sys
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import relatorios_setor as rs  # noqa: E402

s = rs.session()
try:
    s.get(rs.FENABRAVE_HOME, timeout=30)
except Exception as e:  # noqa: BLE001
    print("home", e)
url = rs.fenabrave_latest(s)
print("URL", url)
r = s.get(url, timeout=90)
print("PDF", r.status_code, len(r.content))
with pdfplumber.open(io.BytesIO(r.content)) as pdf:
    print("pages", len(pdf.pages))
    for i, pg in enumerate(pdf.pages):
        t = pg.extract_text() or ""
        up = t.upper()
        if any(k in up for k in ("RANDON", "LIBRELATO", "FACCHINI", "IMPLEMENTO", "REBOQUE", "SEMIRREBOQUE", "SEMI-REBOQUE")):
            print(f"===== page {i + 1}")
            print(t[:4000])
