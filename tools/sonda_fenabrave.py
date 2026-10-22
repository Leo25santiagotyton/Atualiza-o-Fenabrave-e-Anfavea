"""Sonda temporária: mercado de usados e seminovos (Fenauto)."""
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from monitor import BROWSER_HEADERS  # noqa: E402

s = requests.Session()
s.headers.update(BROWSER_HEADERS)
for url in ["https://www.fenauto.org.br/news/", "https://www.fenauto.org.br/news/categoria/novidades", "https://www.fenauto.org.br/"]:
    try:
        r = s.get(url, timeout=40)
    except Exception as e:
        print("ERRO", url, e)
        continue
    print("==", url, r.status_code, len(r.text))
    soup = BeautifulSoup(r.text, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        t = " ".join(a.get_text(" ").split())
        h = requests.compat.urljoin(url, a["href"])
        if re.search(r"usad|semin|transfer|vend|mercado|\.pdf", t + " " + h, re.I) and len(t) > 10:
            links.append((t[:110], h))
    for t, h in dict.fromkeys(links):
        print("  ", t, "|", h)
    noticias = [h for t, h in links if "/news/" in h and "categoria" not in h]
    for h in list(dict.fromkeys(noticias))[:3]:
        try:
            rr = s.get(h, timeout=40)
            txt = " ".join(BeautifulSoup(rr.text, "html.parser").get_text(" ").split())
            i = max(0, txt.find("transfer") - 300)
            print("#### ", h, rr.status_code)
            print(txt[i:i + 5000])
        except Exception as e:
            print("ERRO", h, e)
    break
