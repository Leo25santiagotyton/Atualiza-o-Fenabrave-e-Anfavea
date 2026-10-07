"""Sonda temporária: links da ANFAVEA (Carta e estatísticas) para achar o resultado mais novo."""
import re, requests
from bs4 import BeautifulSoup
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
for u in ["https://anfavea.com.br/site/conteudos/carta-da-anfavea/", "https://anfavea.com.br/site/", "https://anfavea.com.br/site/estatisticas/",
          "https://anfavea.com.br/site/edicoes-em-excel/", "https://anfavea.com.br/site/category/noticias/"]:
    try:
        r = requests.get(u, headers=H, timeout=30)
        print("=====", r.status_code, u)
        s = BeautifulSoup(r.text, "html.parser")
        for a in s.find_all("a", href=True):
            h = a["href"]; t = a.get_text(" ", strip=True)
            if re.search(r"\.pdf|\.xlsx?|carta|resultad|setembro|emplacament|produ", h + " " + t, re.I):
                print("  ", t[:80], "|", h[:160])
    except Exception as e:
        print("ERRO", u, e)
for n in (485, 486):
    for base in ("https://anfavea.com.br/site/wp-content/uploads/cartas/carta%d.pdf", "https://www.anfavea.com.br/cartas/carta%d.pdf", "https://anfavea.com.br/cartas/carta%d.pdf"):
        u = base % n
        try:
            r = requests.get(u, headers=H, timeout=30, stream=True)
            print(r.status_code, r.headers.get("content-type"), u)
        except Exception as e:
            print("ERRO", u, e)
