"""
Dólar futuro (DOL) e FRC de cupom cambial na B3
-----------------------------------------------
Fonte: Boletim de Preços da B3 (arquivo PRAAMMDD da Pesquisa por Pregão, XML BVBG.086.01),
com o ajuste e as cotações do dia de todos os derivativos. Daqui saem:
  DOL<mês><ano>  dólar comercial futuro (R$ por US$ 1.000) · ajuste, último, volume
  FRC<mês><ano>  FRA de cupom cambial (% a.a. linear 360) · taxa de ajuste, última taxa
  DDI<mês><ano>  cupom cambial sujo (quando houver)

O arquivo vem como zip dentro de zip; o interno às vezes usa Deflate64, que o zipfile do Python
não lê, então caímos no `unzip` do sistema.
"""

import io
import re
import subprocess
import tempfile
import zipfile
from datetime import date
from pathlib import Path
from xml.etree.ElementTree import iterparse

URL = "https://www.b3.com.br/pesquisapregao/download?filelist=PR{d:%y%m%d}.zip,"
MONTHS = "FGHJKMNQUVXZ"
TICKER = re.compile(r"^(DOL|FRC|DDI)([FGHJKMNQUVXZ])(\d{2})$")


def _xml_blobs(blob, depth=0):
    """Todos os .xml de dentro do arquivo (zip dentro de zip)."""
    if depth > 4:
        return
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
        names = zf.namelist()
    except zipfile.BadZipFile:
        if blob[:5] == b"<?xml":
            yield blob
        return
    for n in names:
        try:
            data = zf.read(n)
        except NotImplementedError:  # Deflate64
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / "a.zip"
                p.write_bytes(blob)
                data = subprocess.run(["unzip", "-p", str(p), n], capture_output=True, check=True).stdout
        if n.lower().endswith(".xml"):
            yield data
        else:
            yield from _xml_blobs(data, depth + 1)


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def maturity(month_code, yy):
    """Vencimento de referência: 1º dia útil do mês do contrato (aprox., sem feriados)."""
    d = date(2000 + int(yy), MONTHS.index(month_code) + 1, 1)
    while d.weekday() >= 5:
        d = d.replace(day=d.day + 1)
    return d


def parse_prices(xml_bytes):
    """{ticker: {campo: valor}} para DOL/FRC/DDI a partir do BVBG.086."""
    out = {}
    rec, tck, in_attr = {}, None, False
    for ev, el in iterparse(io.BytesIO(xml_bytes), events=("start", "end")):
        tag = _local(el.tag)
        if ev == "start":
            if tag == "PricRpt":
                rec, tck = {}, None
            elif tag == "FinInstrmAttrbts":
                in_attr = True
            continue
        if tag == "TckrSymb":
            tck = (el.text or "").strip()
        elif in_attr and tag != "FinInstrmAttrbts" and el.text and el.text.strip():
            rec[tag] = el.text.strip()
        elif tag == "FinInstrmAttrbts":
            in_attr = False
        elif tag == "PricRpt":
            if tck and TICKER.match(tck):
                out[tck] = dict(rec)
            el.clear()
    return out


def fetch_usd_market(session, d):
    """{'date', 'DOL': [[ticker, venc, ajuste, último, contratos]], 'FRC': [[ticker, venc, taxa ajuste, última taxa, contratos]], ...}"""
    r = session.get(URL.format(d=d), timeout=120)
    if r.status_code != 200 or len(r.content) < 1000:
        print(f"[AVISO] Boletim de preços B3 {d}: status {r.status_code}, {len(r.content)} bytes")
        return {}
    prices = {}
    for xml in _xml_blobs(r.content):
        prices.update(parse_prices(xml))
    if not prices:
        print(f"[AVISO] Boletim de preços B3 {d}: nenhum DOL/FRC encontrado")
        return {}
    for sym in ("DOL", "FRC", "DDI"):
        k = next((t for t in sorted(prices) if t.startswith(sym)), None)
        if k:
            print(f"[INFO] B3 {d} {k}: campos {prices[k]}")
    out = {"date": d.isoformat()}
    for tck, f in prices.items():
        sym, m, yy = TICKER.match(tck).groups()
        adj = _num(f.get("AdjstdQt") or f.get("AdjstdQtTax") or f.get("AdjstdValCtrct"))
        if sym in ("FRC", "DDI"):
            adj = _num(f.get("AdjstdQtTax") or f.get("AdjstdQt"))
            last = _num(f.get("LastPric") or f.get("MaxTradLmt"))
        else:
            last = _num(f.get("LastPric"))
        qty = _num(f.get("FinInstrmQty") or f.get("RglrTxsQty") or f.get("OpnIntrst"))
        out.setdefault(sym, []).append([tck, maturity(m, yy).isoformat(), adj, last, qty])
    for sym in ("DOL", "FRC", "DDI"):
        if sym in out:
            out[sym].sort(key=lambda x: x[1])
    print(f"[INFO] B3 {d}: {len(out.get('DOL', []))} DOL, {len(out.get('FRC', []))} FRC, {len(out.get('DDI', []))} DDI")
    return out


if __name__ == "__main__":
    import sys
    import requests

    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    d = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    res = fetch_usd_market(s, d)
    for k in ("DOL", "FRC", "DDI"):
        print(k, res.get(k, [])[:8])
