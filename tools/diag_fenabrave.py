"""Diagnóstico temporário: estrutura do release FENABRAVE e do site ANFAVEA."""
import sys, re
sys.path.insert(0, ".")
import requests
from bs4 import BeautifulSoup
from monitor import BROWSER_HEADERS

s = requests.Session()
s.headers.update(BROWSER_HEADERS)

def show(url, text=True, links=True, maxc=15000):
    print("=" * 100)
    try:
        r = s.get(url, timeout=40)
        print(url, r.status_code, r.url, r.headers.get("content-type"), len(r.content))
        if "html" not in (r.headers.get("content-type") or ""):
            return r
        soup = BeautifulSoup(r.text, "html.parser")
        if len(r.text) < 2000:
            print("RAW:", r.text)
        if links:
            for a in soup.find_all("a", href=True):
                h = a["href"]
                if any(k in h.lower() for k in ["pdf", "xls", "noticia/1749", "emplac", "estat", "carta", "dados", "download", "upload"]):
                    print("  LINK", h[:200], "|", " ".join(a.get_text(" ", strip=True).split())[:100])
        for t in soup.find_all("table"):
            print("  TABLE:", " ".join(t.get_text(" | ", strip=True).split())[:3000])
        if text:
            for tag in soup(["script", "style", "nav", "header", "footer"]):
                tag.decompose()
            body = "\n".join(l.strip() for l in soup.get_text("\n").splitlines() if l.strip())
            i = body.find("Emplacamentos de veículos batem")
            print("TEXT:", body[max(i, 0):max(i, 0) + maxc])
        return r
    except Exception as e:
        print(url, "ERRO", e)

s.get("https://www.fenabrave.org.br/portalv2/home/imprensa", timeout=30)
show("https://www.fenabrave.org.br/portalv2/Noticia/17490")
show("https://www.fenabrave.org.br/portalv2/Conteudo/emplacamentos", text=False)
for u in ["https://anfavea.com.br/", "https://www.anfavea.com.br/", "https://anfavea.com.br/site/",
          "https://anfavea.com.br/site/edicoes-em-excel/", "https://anfavea.com.br/site/estatisticas/",
          "https://anfavea.com.br/site/carta-da-anfavea/", "https://www.anfavea.com.br/estatisticas"]:
    show(u, text=False)
