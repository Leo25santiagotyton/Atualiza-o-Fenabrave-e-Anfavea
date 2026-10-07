"""Sonda temporária: procura o release ANFAVEA de outubro/2026 (dados de setembro)."""
import re, io, requests, pdfplumber
from bs4 import BeautifulSoup
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}

def pdf(u, n=6):
    try:
        pr = requests.get(u, headers=H, timeout=60); print("PDF", pr.status_code, len(pr.content), u)
        if pr.status_code != 200: return
        with pdfplumber.open(io.BytesIO(pr.content)) as p:
            for i, pg in enumerate(p.pages[:n]):
                print(f"--- p{i+1}"); print((pg.extract_text() or "")[:2000])
    except Exception as e:
        print("ERRO", u, e)

for u in ["https://anfavea.com.br/site/imprensa-noticia/coletiva-de-imprensa-outubro-2026/",
          "https://anfavea.com.br/site/imprensa/", "https://anfavea.com.br/site/",
          "https://anfavea.com.br/site/edicoes-em-excel/", "https://anfavea.com.br/site/conteudos/carta-da-anfavea/"]:
    try:
        r = requests.get(u, headers=H, timeout=30); print("==", r.status_code, u)
        s = BeautifulSoup(r.text, "html.parser")
        for a in s.find_all("a", href=True):
            t = a.get_text(" ", strip=True)
            if re.search(r"coletiva|outubro|setembro|carta|\.pdf|\.xlsx?|uploads/2026/1", t + a["href"], re.I):
                print("LINK", t[:70], "|", a["href"])
    except Exception as e:
        print("ERRO", u, e)

for u in ["https://anfavea.com.br/site/wp-content/uploads/2026/10/COLETIVA_OUTUBRO26.pdf",
          "https://anfavea.com.br/docs/cartas/carta485.pdf",
          "https://anfavea.com.br/docs/cartas/carta484.pdf"]:
    pdf(u, 3)
