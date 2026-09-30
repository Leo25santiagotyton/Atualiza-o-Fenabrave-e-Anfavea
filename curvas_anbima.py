"""
Curvas de referência para trocar (swapar) taxas IPCA+ em NTN-B + e CDI +
------------------------------------------------------------------------
- NTN-B e prefixados (LTN/NTN-F): arquivo diário de títulos públicos da ANBIMA
  (merc-sec/arqs/msAAMMDD.txt), taxa indicativa por vencimento.
- Curva DI x Pré: taxas referenciais da B3 (dias corridos, base 252).

Conversão de um papel IPCA + r com duration D (dias úteis):
  NTN-B +  = (1 + r) / (1 + taxa indicativa da NTN-B de referência) − 1
             (a NTN-B que a ANBIMA indica para o papel; se não houver, a curva
             de NTN-B interpolada na duration)
  CDI +    = inflação implícita π(D) da ETTJ ANBIMA
             taxa nominal = (1 + r)(1 + π) − 1
             CDI + = (1 + nominal) / (1 + DI(D)) − 1
             DI(D): curva DI x Pré da B3 quando disponível; senão a ETTJ prefixada
             da ANBIMA como aproximação.
"""

import re
import unicodedata
from datetime import date, datetime, timedelta



ETTJ_URL = "https://www.anbima.com.br/informacoes/est-termo/CZ-down.asp"
TITULOS_URL = "https://www.anbima.com.br/informacoes/merc-sec/arqs/ms{d:%y%m%d}.txt"
DI_URL = ("https://www2.bmf.com.br/pages/portal/bmfbovespa/lumis/lum-taxas-referenciais-bmf-ptBR.asp"
          "?Data={d:%d/%m/%Y}&Data1={d:%Y%m%d}&slcTaxa=PRE")


def _norm(s):
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).upper().strip()


def _num(s):
    s = (s or "").strip()
    if not s or s in {"--", "-"}:
        return None
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _date(s):
    s = (s or "").strip()
    for fmt in ("%d/%m/%Y", "%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def du_between(a, b):
    """Dias úteis aproximados (sem feriados) entre duas datas."""
    if b <= a:
        return 0
    days = (b - a).days
    weeks, rest = divmod(days, 7)
    du = weeks * 5
    wd = a.weekday()
    for i in range(1, rest + 1):
        if (wd + i) % 7 < 5:
            du += 1
    return du


def fetch_titulos(session, d):
    """{'ntnb': [(venc, du, taxa)], 'pre': [(venc, du, taxa)]} ou None se não houver arquivo."""
    r = session.get(TITULOS_URL.format(d=d), timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    text = r.content.decode("latin-1")
    cols, out = None, {"ntnb": [], "pre": []}
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("@")]
        if len(parts) < 5:
            continue
        head = [_norm(p) for p in parts]
        if head[0].startswith("TITULO"):
            cols = head
            continue
        if not cols:
            continue

        def col(prefix):
            for i, h in enumerate(cols):
                if h.startswith(prefix) and i < len(parts):
                    return parts[i]
            return ""

        titulo = _norm(parts[0])
        venc = _date(col("DATA VENC"))
        taxa = _num(col("TX. INDICATIVA"))
        if not venc or taxa is None:
            continue
        item = (venc.isoformat(), du_between(d, venc), taxa)
        if titulo == "NTN-B":
            out["ntnb"].append(item)
        elif titulo in ("LTN", "NTN-F"):
            out["pre"].append(item)
    if not out["ntnb"]:
        print(f"[AVISO] títulos públicos {d}: NTN-B não encontrada. Início do arquivo:\n{text[:600]}")
    for k in out:
        out[k].sort(key=lambda x: x[1])
    return out


def fetch_di_pre(session, d):
    """[(dias corridos, taxa 252)] da curva DI x Pré da B3, ou [] se indisponível."""
    r = session.get(DI_URL.format(d=d), timeout=30)
    r.raise_for_status()
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(r.content, "html.parser")
    cells = [td.get_text(strip=True) for td in soup.find_all("td")]
    curve = []
    for i in range(0, len(cells) - 2):
        dc, t252 = cells[i], cells[i + 1]
        if re.fullmatch(r"\d{1,5}", dc) and re.fullmatch(r"\d{1,2},\d{2,4}", t252) and re.fullmatch(r"\d{1,2},\d{2,4}", cells[i + 2]):
            curve.append((int(dc), _num(t252)))
    # remove repetidos mantendo a ordem
    seen, uniq = set(), []
    for dc, t in curve:
        if dc not in seen:
            seen.add(dc)
            uniq.append((dc, t))
    if not uniq:
        print(f"[AVISO] curva DI x Pré {d}: não encontrada. Início da página:\n{r.text[:600]}")
    return sorted(uniq)


def fetch_ettj(session, d):
    """[(du, ipca_real, pre, inflacao_implicita)] da ETTJ ANBIMA do dia, ou []."""
    r = session.post(ETTJ_URL, data={"Idioma": "PT", "Dt_Ref": d.strftime("%d/%m/%Y"), "saida": "csv"}, timeout=30)
    r.raise_for_status()
    text = r.content.decode("latin-1")
    out, on = [], False
    for line in text.splitlines():
        parts = [x.strip() for x in line.split(";")]
        if parts and _norm(parts[0]).startswith("VERTICES"):
            on = True
            continue
        if on:
            if len(parts) < 4 or not re.fullmatch(r"[\d.]+", parts[0]):
                if out:
                    break
                continue
            du = int(parts[0].replace(".", ""))
            vals = [_num(x) for x in parts[1:4]]
            if None not in vals:
                out.append((du, *vals))
    if not out:
        print(f"[AVISO] ETTJ {d}: vértices não encontrados. Início:\n{text[:400]}")
    return out


def interp(points, x):
    """Interpolação linear da taxa por prazo (points = [(prazo, taxa)]), extrapolação plana."""
    if not points:
        return None
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0) if x1 != x0 else y0
    return points[-1][1]


def swap_ipca(rate, duration_du, ntnb_ref, tit, di, ettj=None):
    """(NTN-B + equivalente em %, CDI + equivalente em %) para um papel IPCA + rate."""
    if rate is None or duration_du is None or not tit or not tit["ntnb"]:
        return None, None
    ntnb_curve = [(du, t) for _, du, t in tit["ntnb"] if du > 0]
    ref = None
    ref_date = _date(ntnb_ref or "")
    if ref_date:
        ref = next((t for v, _, t in tit["ntnb"] if v == ref_date.isoformat()), None)
    if ref is None:
        ref = interp(ntnb_curve, duration_du)
    spread_ntnb = ((1 + rate / 100) / (1 + ref / 100) - 1) * 100 if ref is not None else None

    return spread_ntnb, cdi_equivalente(rate, duration_du, tit, di, ettj)


def cdi_equivalente(rate, duration_du, tit=None, di=None, ettj=None):
    """CDI + equivalente (%) de uma taxa IPCA + rate com duration em dias úteis."""
    if rate is None or duration_du is None:
        return None
    if ettj:
        infl = interp([(e[0], e[3]) for e in ettj], duration_du)
        pre = interp([(e[0], e[2]) for e in ettj], duration_du)
    elif tit and tit.get("pre") and tit.get("ntnb"):
        pre = interp([(du, t) for _, du, t in tit["pre"] if du > 0], duration_du)
        real = interp([(du, t) for _, du, t in tit["ntnb"] if du > 0], duration_du)
        infl = ((1 + pre / 100) / (1 + real / 100) - 1) * 100 if pre is not None and real is not None else None
    else:
        return None
    di_rate = interp(di, duration_du * 365 / 252) if di else pre
    if infl is None or di_rate is None:
        return None
    nominal = (1 + rate / 100) * (1 + infl / 100) - 1
    return ((1 + nominal) / (1 + di_rate / 100) - 1) * 100
