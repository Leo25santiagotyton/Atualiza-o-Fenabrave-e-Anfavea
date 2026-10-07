"""Sonda temporária: páginas de dados de caminhões dos EUA."""
import re, requests
from bs4 import BeautifulSoup
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
     "Accept-Language": "en-US,en;q=0.9"}
URLS = [
    "https://www.actresearch.net/resources/press-releases",
    "https://www.actresearch.net/news",
    "https://www.ftrintel.com/press-releases",
    "https://www.ftrintel.com/news",
    "https://www.nada.org/atd",
    "https://www.nada.org/atd/news",
    "https://www.trucknews.com/",
]
for u in URLS:
    try:
        r = requests.get(u, headers=H, timeout=30)
        print("=====", u, r.status_code, r.url, len(r.text))
        s = BeautifulSoup(r.text, "html.parser")
        n = 0
        for a in s.find_all("a", href=True):
            t = a.get_text(" ", strip=True)
            if re.search(r"class 8|order|truck|trailer|classes 5|class 5|vocational", t, re.I):
                print("  ", t[:120], "|", a["href"][:150]); n += 1
                if n >= 25: break
    except Exception as e:
        print("=====", u, "ERRO", e)
