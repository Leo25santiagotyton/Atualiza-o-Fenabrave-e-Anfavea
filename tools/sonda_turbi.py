"""Sonda temporária: páginas da FENABRAVE e da ANFAVEA (links de PDF)."""
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import relatorios_setor as rs  # noqa: E402

s = rs.session()
try:
    s.get(rs.FENABRAVE_HOME, timeout=30)
except Exception as e:
    print("home", e)
for url in [rs.FENABRAVE_PAGE, "https://www.fenabrave.org.br/portalv2/Noticia/17491",
            "https://www.fenabrave.org.br/portalv2/Conteudo/Emplacamentos", rs.ANFAVEA_HOME, rs.ANFAVEA_PAGE]:
    try:
        r = s.get(url, timeout=40)
    except Exception as e:
        print("ERRO", url, e)
        continue
    print("==", url, r.status_code, len(r.text), r.url)
    soup = BeautifulSoup(r.text, "html.parser")
    vistos = set()
    for a in soup.find_all("a", href=True):
        h = requests.compat.urljoin(url, a["href"])
        if re.search(r"\.pdf|/files/|upload|informativo|emplac|coletiva|release|carta", h, re.I) and h not in vistos:
            vistos.add(h)
            print("  ", " ".join(a.get_text(" ").split())[:80], "|", h)
    for m in sorted(set(re.findall(r"[\w/:.\-]*20\d\d_\d\d_\d+\.pdf", r.text)))[:40]:
        print("  raw:", m)
try:
    print("latest fenabrave:", rs.fenabrave_latest(s))
except Exception as e:
    print("latest fenabrave ERRO", e)
for mes in range(1, 6):
    u = f"https://www.fenabrave.org.br/portal/files/2026_10_0{mes}.pdf"
    try:
        r = s.get(u, timeout=30)
        print(u, r.status_code, r.headers.get("content-type"), len(r.content))
    except Exception as e:
        print(u, e)
