"""Sonda temporária: ANFIR (implementos rodoviários) e Comex Stat (NCM 8716 reboques/semirreboques)."""
import json
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from monitor import BROWSER_HEADERS  # noqa: E402

s = requests.Session()
s.headers.update(BROWSER_HEADERS)
for url in ["https://www.anfir.org.br/", "https://anfir.org.br/estatisticas/", "https://www.anfir.org.br/estatisticas",
            "https://anfir.org.br/emplacamentos/", "https://anfir.org.br/noticias/"]:
    try:
        r = s.get(url, timeout=40)
    except Exception as e:
        print("ERRO", url, e); continue
    print("==", url, r.status_code, len(r.text), r.url)
    vistos = set()
    for a in BeautifulSoup(r.text, "html.parser").find_all("a", href=True):
        h = requests.compat.urljoin(r.url, a["href"]); t = " ".join(a.get_text(" ").split())[:90]
        if re.search(r"estat|emplac|\.pdf|\.xls|dados|mercado|reboque|resultado|balan|noticia", h + " " + t, re.I) and h not in vistos:
            vistos.add(h); print("  ", t, "|", h)

# Comex Stat API
api = "https://api-comexstat.mdic.gov.br"
for path in ["/general/dates/updated", "/tables/ncm?search=8716"]:
    try:
        r = requests.get(api + path, timeout=40, headers={"Accept": "application/json"})
        print("==", path, r.status_code, r.text[:1500])
    except Exception as e:
        print("ERRO", path, e)
body = {"flow": "export", "monthDetail": True, "period": {"from": "2025-01", "to": "2026-12"},
        "filters": [{"filter": "ncm", "values": ["87163100", "87163900", "87164000", "87162000"]}],
        "details": ["ncm"], "metrics": ["metricFOB", "metricKG", "metricStatistic"]}
for flow in ("export", "import"):
    body["flow"] = flow
    try:
        r = requests.post(api + "/general", json=body, timeout=60, headers={"Accept": "application/json"})
        print("== general", flow, r.status_code, r.text[:2500])
    except Exception as e:
        print("ERRO general", flow, e)
