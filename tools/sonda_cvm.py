"""Sonda temporária: página da coletiva ANFAVEA Setembro/2026."""
import re, io, requests, pdfplumber
from bs4 import BeautifulSoup
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
u = "https://anfavea.com.br/site/imprensa-noticia/coletiva-de-imprensa-setembro-2026/"
r = requests.get(u, headers=H, timeout=30); print(r.status_code)
s = BeautifulSoup(r.text, "html.parser")
main = s.find("article") or s.find("main") or s
print(main.get_text("\n", strip=True)[:4000])
for a in s.find_all("a", href=True):
    if re.search(r"\.pdf|\.pptx?|\.xlsx?|apresenta|wp-content/uploads", a["href"], re.I):
        print("LINK", a.get_text(" ", strip=True)[:60], "|", a["href"])
        if a["href"].lower().endswith(".pdf"):
            try:
                pr = requests.get(a["href"], headers=H, timeout=60)
                with pdfplumber.open(io.BytesIO(pr.content)) as pdf:
                    for i, p in enumerate(pdf.pages[:8]):
                        print(f"--- pdf p{i+1}"); print((p.extract_text() or "")[:2500])
            except Exception as e:
                print("ERRO pdf", e)
