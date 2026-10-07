"""Sonda temporária: arquivo público (sem reCAPTCHA) com taxas indicativas de CRI/CRA da ANBIMA."""
import re, requests
from datetime import date, timedelta
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
d = date.today() - timedelta(days=1)
while d.weekday() >= 5: d -= timedelta(days=1)
URLS = [
 "https://www.anbima.com.br/pt_br/informar/precos-e-indices/precos/taxas-de-cri-e-cra.htm",
 "https://www.anbima.com.br/pt_br/informar/precos-e-indices/precos/cri-e-cra.htm",
 "https://www.anbima.com.br/informacoes/merc-sec-cri-cra/default.asp",
 "https://www.anbima.com.br/informacoes/merc-sec-cri/default.asp",
 "https://www.anbima.com.br/informacoes/merc-sec-cra/default.asp",
 f"https://www.anbima.com.br/informacoes/merc-sec-cri-cra/arqs/cri{d:%y%m%d}.txt",
 f"https://www.anbima.com.br/informacoes/merc-sec-cri-cra/arqs/cra{d:%y%m%d}.txt",
 f"https://www.anbima.com.br/informacoes/merc-sec-cri-cra/arqs/cc{d:%y%m%d}.txt",
 "https://www.anbima.com.br/informacoes/merc-sec-debentures/default.asp",
 "https://www.anbima.com.br/pt_br/informar/precos-e-indices.htm",
]
for u in URLS:
    try:
        r = requests.get(u, headers=H, timeout=30)
        t = r.text
        print("=====", r.status_code, len(t), u)
        for m in re.finditer(r'href="([^"]*(?:cri|cra|CRI|CRA)[^"]*)"', t):
            print("   link:", m.group(1)[:160])
        if r.status_code == 200 and len(t) < 4000: print(t[:1500])
    except Exception as e:
        print("=====", "ERRO", u, e)
