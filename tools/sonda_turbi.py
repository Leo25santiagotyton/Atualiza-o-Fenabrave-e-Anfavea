"""Sonda temporária: lista de filiais da Priner e malha IBGE."""
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from monitor import BROWSER_HEADERS  # noqa: E402

s = requests.Session()
s.headers.update(BROWSER_HEADERS)
r = s.get("https://www.priner.com.br/contato/", timeout=40)
txt = " ".join(BeautifulSoup(r.text, "html.parser").get_text(" ").split())
i = txt.find("Conheça nossa matriz")
print("FILIAIS", txt[i:i + 6000])
r = requests.get("https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR", params={"formato": "application/vnd.geo+json", "qualidade": "minima", "intrarregiao": "UF"}, timeout=60)
print("IBGE", r.status_code, len(r.content), r.text[:200].replace("\n", " "))
