"""Sonda temporária: página inicial e imprensa da ANFAVEA (coletiva nova)."""
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import relatorios_setor as rs  # noqa: E402

s = rs.session()
for url in [rs.ANFAVEA_HOME, "https://anfavea.com.br/site/imprensa/", "https://anfavea.com.br/site/category/imprensa/",
            "https://anfavea.com.br/site/imprensa-noticia/coletiva-de-imprensa-novembro-2026/", rs.ANFAVEA_PAGE]:
    try:
        r = s.get(url, timeout=40)
    except Exception as e:
        print("ERRO", url, e)
        continue
    print("==", url, r.status_code, len(r.text), r.url)
    vistos = set()
    for a in BeautifulSoup(r.text, "html.parser").find_all("a", href=True):
        h = requests.compat.urljoin(url, a["href"])
        t = " ".join(a.get_text(" ").split())[:90]
        if re.search(r"coletiva|release|\.pdf|imprensa-noticia|carta|novembro|outubro|resultado", h + " " + t, re.I) and h not in vistos:
            vistos.add(h)
            print("  ", t, "|", h)
try:
    print("coletiva():", rs.anfavea_coletiva(s))
except Exception as e:
    print("coletiva ERRO", e)
