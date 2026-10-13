"""Sonda temporária: cores de marca dos emissores (theme-color e cores mais usadas no CSS do site)."""
import re, requests, collections
from urllib.parse import urljoin
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
SITES = {"Vamos": ["https://grupovamos.com.br/", "https://www.vamos.com.br/", "https://ri.grupovamos.com.br/"],
         "Priner": ["https://www.priner.com.br/", "https://ri.priner.com.br/"],
         "OHI": ["https://www.omnihelicoptersinternational.com/", "https://omnibrasil.com.br/"]}
for emp, urls in SITES.items():
    for u in urls:
        try:
            r = requests.get(u, headers=H, timeout=40)
            html = r.text
            css = html
            for href in re.findall(r'<link[^>]+href="([^"]+\.css[^"]*)"', html)[:6]:
                try:
                    css += requests.get(urljoin(u, href), headers=H, timeout=30).text
                except Exception:
                    pass
            tc = re.findall(r'name="theme-color"\s+content="([^"]+)"', html)
            cs = collections.Counter(c.lower() for c in re.findall(r"#[0-9a-fA-F]{6}\b", css))
            cs = [c for c, _ in cs.most_common(40) if c not in ("#ffffff", "#000000")][:12]
            print(f"::notice title={emp}::{u} status={r.status_code} theme={tc} top={cs}")
        except Exception as e:
            print(f"::notice title={emp}::{u} erro {e}")
