"""
Curvas de swap da B3 ("Taxas de Mercado para Swaps", arquivo TaxaSwap)
----------------------------------------------------------------------
Publicado todo dia útil na Pesquisa por Pregão da B3. Dele usamos:
  PRE  – curva DI x Pré (taxa ao ano, base 252)
  DIC  – cupom de IPCA do swap DI x IPCA (juro real do mercado de derivativos)

Com elas o CDI + de um papel IPCA + r na duration D fica
  π(D)   = (1 + PRE(D)) / (1 + DIC(D)) − 1           (inflação implícita do swap)
  CDI +  = (1 + r)(1 + π(D)) / (1 + PRE(D)) − 1       = (1 + r) / (1 + DIC(D)) − 1

Layout do registro (posições do manual da B3, 1-based):
  data geração 9–16 · código da curva 19–23 · dias corridos 39–43 · dias de saques 44–48
  sinal 49 · taxa teórica 50–63 (7 casas decimais)
"""

import io
import re
import zipfile

URLS = [
    "https://www.b3.com.br/pesquisapregao/download?filelist=TS{d:%y%m%d}.ex_,",
    "https://www.b3.com.br/pesquisapregao/download?filelist=TS{d:%y%m%d}.ex_",
]


def _unzip_all(blob, depth=0):
    """Abre zip dentro de zip (o .ex_ da B3 é um zip) e devolve o texto do primeiro .txt."""
    if depth > 3:
        return None
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        return None
    for name in zf.namelist():
        data = zf.read(name)
        if name.lower().endswith(".txt"):
            return data.decode("latin-1")
        inner = _unzip_all(data, depth + 1)
        if inner:
            return inner
    return None


def parse_taxa_swap(text):
    """{codigo: [(dias_corridos, dias_uteis, taxa_%)]} a partir do texto do TaxaSwap."""
    out = {}
    for line in text.splitlines():
        if len(line) < 63 or not line[:6].strip().isdigit():
            continue
        code = line[18:23].strip()
        try:
            dc = int(line[38:43])
            du = int(line[43:48])
            val = int(line[49:63]) / 1e7
        except ValueError:
            continue
        if line[48:49] == "-":
            val = -val
        out.setdefault(code, []).append((dc, du, val))
    for k in out:
        out[k].sort()
    return out


def fetch_taxa_swap(session, d):
    """Curvas PRE e DIC do dia (dias úteis → taxa %), ou {} se não houver arquivo."""
    last = None
    for u in URLS:
        try:
            r = session.get(u.format(d=d), timeout=60)
            if r.status_code != 200 or len(r.content) < 200:
                last = f"status {r.status_code}, {len(r.content)} bytes"
                continue
            text = _unzip_all(r.content) or (r.content.decode("latin-1") if re.match(rb"\d{6}", r.content[:6]) else None)
            if not text:
                last = f"conteúdo não reconhecido ({r.headers.get('content-type')}, {r.content[:60]!r})"
                continue
            curves = parse_taxa_swap(text)
            if not curves.get("PRE"):
                last = f"curvas no arquivo: {sorted(curves)[:20]}; início: {text[:200]!r}"
                continue
            return {k: [(du, v) for _, du, v in pts if du > 0] for k, pts in curves.items() if k in ("PRE", "DIC", "DOC", "DIM")}
        except Exception as e:
            last = str(e)
    print(f"[AVISO] TaxaSwap B3 {d}: {last}")
    return {}
