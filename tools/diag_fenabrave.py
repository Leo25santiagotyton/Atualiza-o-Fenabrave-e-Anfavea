"""Diagnóstico temporário: lista os links das páginas da FENABRAVE e da ANFAVEA."""
import requests
from bs4 import BeautifulSoup

import sys
sys.path.insert(0, ".")
from monitor import BROWSER_HEADERS

URLS = [
    ("https://www.fenabrave.org.br/", None),
    ("https://www.fenabrave.org.br/portalv2/home/imprensa", "https://www.fenabrave.org.br/"),
    ("https://anfavea.com.br/", None),
]

s = requests.Session()
s.headers.update(BROWSER_HEADERS)
for url, ref in URLS:
    print("=" * 100)
    try:
        r = s.get(url, timeout=30, headers={"Referer": ref} if ref else {})
        print(url, r.status_code, r.url, len(r.text))
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            t = " ".join(a.get_text(" ", strip=True).split())[:120]
            print(f"  {a['href'][:150]} | {t}")
    except Exception as e:
        print(url, "ERRO", e)
