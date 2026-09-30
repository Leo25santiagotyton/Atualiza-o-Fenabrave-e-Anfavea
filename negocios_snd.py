"""
Negócios de debêntures no secundário (SND / debentures.com.br)
--------------------------------------------------------------
Lê a consulta "Preços de Negociação" do SND para um dia e devolve, por papel,
quantidade negociada, número de negócios, PU mínimo/médio/máximo e % do PU da curva.
"""

import re
import unicodedata

from bs4 import BeautifulSoup

SND_URL = ("https://www.debentures.com.br/exploreosnd/consultaadados/mercadosecundario/"
           "precosdenegociacao_r.asp?op_exc=False&emissor=&ativo={ativo}&dt_ini={d:%d/%m/%Y}&dt_fim={d2:%d/%m/%Y}")


def _num(s):
    s = (s or "").strip()
    if not s or s.upper() in {"ND", "--", "-"}:
        return None
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _norm(s):
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).upper().replace("_", " ").strip()


def fetch_trades(session, d, d2=None, ativo=""):
    """Lista de negócios agregados por papel e dia: dicts com date, issuer, code, isin, qty, deals, puMin, puAvg, puMax, pctCurve."""
    r = session.get(SND_URL.format(ativo=ativo, d=d, d2=d2 or d), timeout=60)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "html.parser")
    out = []
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
        cells = [c for c in cells if c != ""]
        if len(cells) < 10 or not re.fullmatch(r"\d{2}/\d{2}/\d{4}", cells[0]):
            continue
        dd, mm, yy = cells[0].split("/")
        out.append({
            "date": f"{yy}-{mm}-{dd}", "issuer": _norm(cells[1]), "code": cells[2].strip(), "isin": cells[3].strip(),
            "qty": _num(cells[4]), "deals": _num(cells[5]),
            "puMin": _num(cells[6]), "puAvg": _num(cells[7]), "puMax": _num(cells[8]), "pctCurve": _num(cells[9]),
        })
    return out


REG_URL = ("https://www.debentures.com.br/exploreosnd/consultaadados/emissoesdedebentures/"
           "caracteristicas_r.asp?tip_deb=publicas&op_exc=False")
PUH_URL = ("https://www.debentures.com.br/exploreosnd/consultaadados/emissoesdedebentures/"
           "puhistorico_r.asp?op_exc=False&ativo={ativo}&dt_ini={a:%d/%m/%Y}&dt_fim={b:%d/%m/%Y}")


def fetch_registered(session):
    """Todas as debêntures registradas no SND: [{code, issuer, status}]."""
    r = session.get(REG_URL, timeout=90)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "html.parser")
    out = []
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
        cells = [c for c in cells if c]
        if len(cells) >= 3 and re.fullmatch(r"[A-Z]{3,5}[A-Z0-9]?\d{1,2}", cells[0]):
            out.append({"code": cells[0], "issuer": _norm(cells[1]), "status": cells[2]})
    return out


def fetch_pu_historico(session, ativo, a, b):
    """PU da curva do SND por dia: [[iso, pu]] em ordem crescente."""
    r = session.get(PUH_URL.format(ativo=ativo, a=a, b=b), timeout=60)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "html.parser")
    out = []
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
        cells = [c for c in cells if c]
        if len(cells) >= 6 and re.fullmatch(r"\d{2}/\d{2}/\d{4}", cells[0]) and cells[1] == ativo:
            dd, mm, yy = cells[0].split("/")
            pu = _num(cells[5])
            if pu is not None:
                out.append([f"{yy}-{mm}-{dd}", pu])
    return sorted(out)
