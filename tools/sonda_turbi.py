"""Sonda temporária: ANFIR dados do setor e notícias."""
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from monitor import BROWSER_HEADERS  # noqa: E402

s = requests.Session()
s.headers.update(BROWSER_HEADERS)
for url in ["https://anfir.org.br/dados-do-setor.php", "https://anfir.org.br/noticias.php",
            "https://anfir.org.br/noticia.php?noticia=3638", "https://anfir.org.br/noticia.php?noticia=3637"]:
    try:
        r = s.get(url, timeout=40)
    except Exception as e:
        print("ERRO", url, e); continue
    print("==", url, r.status_code, len(r.text), r.url, r.headers.get("content-type"))
    soup = BeautifulSoup(r.text, "html.parser")
    vistos = set()
    for a in soup.find_all("a", href=True):
        h = requests.compat.urljoin(r.url, a["href"]); t = " ".join(a.get_text(" ").split())[:100]
        if h not in vistos and not re.search(r"facebook|instagram|linkedin|youtube|twitter|whatsapp|#$", h):
            vistos.add(h); print("  A", t, "|", h)
    for tag in soup.find_all(["iframe", "embed", "object", "img"]):
        src = tag.get("src") or tag.get("data") or ""
        if re.search(r"pdf|xls|grafico|dados|estat|power|tableau|emplac", src, re.I):
            print("  SRC", tag.name, src)
    txt = " ".join(soup.get_text(" ").split())
    i = txt.find("mplacamento")
    print("  TXT", txt[max(0, i - 600): i + 2500] if i >= 0 else txt[:1500])
