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


DET_URL = ("https://www.debentures.com.br/exploreosnd/consultaadados/emissoesdedebentures/"
           "caracteristicas_d.asp?tip_deb=publicas&selecao={ativo}")
AGENDA_BASE = "https://www.debentures.com.br/exploreosnd/consultaadados/eventosfinanceiros/"
AGENDA_URLS = [AGENDA_BASE + "agenda_r.asp?tip_deb=publicas&selecao={ativo}",
               AGENDA_BASE + "agenda_r.asp?op_exc=False&selecao={ativo}&dt_ini=01/01/2000&dt_fim=31/12/2070",
               AGENDA_BASE + "agenda_r.asp?op_exc=False&ativo={ativo}&dt_ini=01/01/2000&dt_fim=31/12/2070"]
DETAIL_LABELS = ["Série/Emissão", "ISIN", "Situação", "Registro CVM da Emissão", "Deb. Incent. (Lei 12.431)", "Garantia/Espécie",
                 "Emissão", "Vencimento", "Data do Novo Vencimento", "Início de Rentabilidade", "Atos Societários", "Emitida",
                 "Mercado", "Resgatada", "Nominal na Emissão", "Coordenador Líder", "Agente Fiduciário", "Tipo de Remuneração",
                 "% Multiplicador/Rentabilidade", "Juros/Spread", "Taxa de Juros", "Prêmio", "Amortização", "Periodicidade",
                 "Tipo de Amortização", "Carência", "Pagamento de Juros"]


def fetch_details(session, ativo):
    """Ficha do papel no SND como pares rótulo → valor (emissão, vencimento, valor nominal, remuneração...)."""
    r = session.get(DET_URL.format(ativo=ativo), timeout=60)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "html.parser")
    out = {}
    # 1) células que terminam em ':' seguidas do valor
    cells = [c.get_text(" ", strip=True) for c in soup.find_all("td")]
    cells = [c for c in cells if c]
    for i, c in enumerate(cells[:-1]):
        if c.endswith(":") and 2 <= len(c) <= 61 and not cells[i + 1].endswith(":"):
            out.setdefault(re.sub(r"\s+", " ", c.rstrip(":").strip()), re.sub(r"\s+", " ", cells[i + 1]).strip(" :"))
    # 2) texto corrido "Rótulo: valor Rótulo: valor" para os rótulos conhecidos
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    alts = "|".join(re.escape(x) for x in sorted(DETAIL_LABELS, key=len, reverse=True))
    for m in re.finditer(rf"(?<![\w/])({alts}):\s*:?\s*(.*?)(?=\s(?:{alts}|IPO|ISIN|[A-ZÀ-Ú][a-zà-ú][A-Za-zÀ-ú.()/% -]{{0,40}}|Artigo \d+º|Nominal em [\d/]+):|$)", text):
        v = m.group(2).strip()
        if v and len(v) <= 200:
            out.setdefault(m.group(1), v)
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
        cells = [c for c in cells if c]
        for i in range(0, len(cells) - 1, 2):
            k, v = cells[i].rstrip(":").strip(), cells[i + 1].strip()
            if 2 <= len(k) <= 60 and v and len(v) <= 300 and not re.fullmatch(r"[\d.,/ -]+", k):
                out.setdefault(k, v)
    return out


def fetch_agenda(session, ativo):
    """Agenda de eventos (juros, amortização, vencimento): [[iso, evento, taxa/percentual, situação]]."""
    r = None
    for u in AGENDA_URLS:
        r = session.get(u.format(ativo=ativo), timeout=60)
        if r.status_code == 200:
            break
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "html.parser")
    out = []
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
        cells = [c for c in cells if c]
        # só linhas do próprio papel (algumas URLs devolvem a agenda de todo o mercado)
        if len(cells) >= 3 and re.fullmatch(r"\d{2}/\d{2}/\d{4}", cells[0]) and ativo in [c.strip() for c in cells]:
            dd, mm, yy = cells[0].split("/")
            rest = [c for c in cells[1:] if c.strip() != ativo]
            out.append([f"{yy}-{mm}-{dd}"] + [c[:60] for c in rest[:4]])
    return out[:400]
