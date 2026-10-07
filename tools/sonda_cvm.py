"""Sonda temporária: de onde tirar os números de pedidos da ACT (Classe 8 e 5-7)."""
import re, requests
from bs4 import BeautifulSoup
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"}
NUM = re.compile(r"[^.]*?(class(es)? ?[5-8][^.]{0,200}?(\d{1,3}(,\d{3})+|\d+(\.\d)?k|\d+(\.\d)? ?thousand)[^.]*\.)", re.I)
def get(u):
    r = requests.get(u, headers=H, timeout=30); return r.status_code, r.text
s, t = get("https://www.actresearch.net/resources/trends-headlines")
soup = BeautifulSoup(t, "html.parser")
links = []
for a in soup.find_all("a", href=True):
    tx = a.get_text(" ", strip=True)
    if re.search(r"order", tx, re.I) and re.search(r"class", tx, re.I) and a["href"].startswith("http"):
        links.append((tx, a["href"].split("?utm")[0]))
for u in ["https://www.actresearch.net/resources/blog/north-america-class-8-blog",
          "https://www.actresearch.net/resources/blog",
          "https://www.actresearch.net/resources/press-releases-news",
          "https://www.ftrintel.com/class-8-truck-orders"]:
    links.append(("DIRETO", u))
seen = set()
for tx, u in links[:14]:
    if u in seen: continue
    seen.add(u)
    try:
        s, t = get(u)
        body = BeautifulSoup(t, "html.parser").get_text(" ", strip=True)
        print("=====", s, len(body), tx[:90], "|", u[:120])
        for m in list(NUM.finditer(body))[:6]:
            print("   >", m.group(1).strip()[:260])
    except Exception as e:
        print("=====", "ERRO", u, e)
