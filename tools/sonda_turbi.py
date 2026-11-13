"""Sonda temporária: como a ANFIR entrega o Anuário (HTML em volta dos links)."""
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from monitor import BROWSER_HEADERS  # noqa: E402

s = requests.Session()
s.headers.update(BROWSER_HEADERS)
r = s.get("https://anfir.org.br/anuario.php", timeout=40)
h = r.text
i = h.find("Anuário 2026")
print("HTML2026", h[max(0, i - 1500): i + 2500])
j = h.find("termo-consentimento")
print("TERMO", h[max(0, j - 300): j + 3000] if j >= 0 else "-")
for m in re.findall(r"""(?:href|data-[a-z-]+|onclick|action)=["']([^"']+)["']""", h):
    if re.search(r"anuario|pdf|download|arquivo|ARQUIVO", m, re.I):
        print("ATTR", m)
r = s.get("https://anfir.org.br/informativo.php", timeout=40)
h = r.text
for m in re.findall(r"""(?:href|data-[a-z-]+|onclick|action)=["']([^"']+)["']""", h):
    if re.search(r"informativo|pdf|download|arquivo|ARQUIVO|edicao", m, re.I):
        print("INF", m)
