"""Sonda temporária: Priner (unidades/filiais), Open-Meteo e malha IBGE."""
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from monitor import BROWSER_HEADERS  # noqa: E402

s = requests.Session()
s.headers.update(BROWSER_HEADERS)
for url in ["https://www.priner.com.br/", "https://www.priner.com.br/unidades/", "https://www.priner.com.br/contato/",
            "https://ri.priner.com.br/a-companhia/perfil-corporativo/", "https://cnpj.biz/18593815000197",
            "https://cnpjbrasil.inf.br/18593815000278"]:
    try:
        r = s.get(url, timeout=40)
    except Exception as e:
        print("ERRO", url, e); continue
    print("==", url, r.status_code, len(r.text), r.url)
    soup = BeautifulSoup(r.text, "html.parser")
    txt = " ".join(soup.get_text(" ").split())
    for kw in ["filia", "unidade", "Unidade", "Filia", "base", "Base", "chuva", "estados", "presença"]:
        for m in list(re.finditer(kw, txt))[:3]:
            print("  ..", txt[max(0, m.start() - 150): m.start() + 350])
    links = {requests.compat.urljoin(r.url, a["href"]) for a in soup.find_all("a", href=True)}
    print("  LINKS", [l for l in links if re.search(r"18593815|unidade|filial|contato|onde", l)][:60])
r = requests.get("https://api.open-meteo.com/v1/forecast", params={"latitude": "-22.78,-12.7", "longitude": "-43.3,-38.3",
                 "daily": "precipitation_sum,precipitation_probability_max", "forecast_days": 16, "past_days": 7, "timezone": "America/Sao_Paulo"}, timeout=40)
print("OPENMETEO", r.status_code, r.text[:500])
r = requests.get("https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR", params={"formato": "application/vnd.geo+json", "qualidade": "minima", "intrarregiao": "UF"}, timeout=60)
print("IBGE", r.status_code, len(r.content), r.text[:300])
r = requests.get("https://servicodados.ibge.gov.br/api/v1/localidades/estados", timeout=60)
print("IBGEUF", r.status_code, r.text[:300])
