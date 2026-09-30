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
    """{curva: [(dias_corridos, dias_uteis, taxa_%)]} a partir do texto do TaxaSwap.

    Layout observado (0-based): 0–5 id · 6–8 compl. · 9–10 tipo · 11–18 data · 19–20 curva a termo ·
    21–25 código da taxa · 26–40 descrição · 41–45 dias corridos · 46–50 dias úteis · 51 sinal ·
    52–65 taxa (7 casas) · 66 característica · 67–71 vértice.
    A curva é indexada pela descrição (ex.: PRE, DIC) e também pelo código numérico."""
    out, names = {}, {}
    for line in text.splitlines():
        if len(line) < 66 or not line[:6].isdigit():
            continue
        code = line[21:26].strip()
        desc = line[26:41].strip()
        try:
            dc, du = int(line[41:46]), int(line[46:51])
            val = int(line[52:66]) / 1e7
        except ValueError:
            continue
        if line[51] == "-":
            val = -val
        key = desc.split()[0].upper() if desc else code
        names[key] = f"{code} {desc}"
        out.setdefault(key, []).append((dc, du, val))
    for k in out:
        out[k].sort()
    parse_taxa_swap.names = names
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
            if not fetch_taxa_swap.logged:
                fetch_taxa_swap.logged = True
                resumo = {k: f"{parse_taxa_swap.names.get(k)} · {len(v)} vértices · 1º {v[0][1]}du={v[0][2]}"
                          for k, v in curves.items()}
                print(f"[INFO] TaxaSwap {d}: curvas encontradas {resumo}")
            if not curves.get("PRE"):
                last = f"sem curva PRE; curvas: {sorted(curves)[:30]}"
                continue
            # escala da taxa: a PRE tem de ficar entre 5% e 30% a.a.
            vals = sorted(v for _, _, v in curves["PRE"])
            med = vals[len(vals) // 2]
            factor = next((f for f in (1, 10, 100, 0.1, 0.01) if 5 <= med * f <= 30), None)
            if factor is None:
                last = f"escala da taxa não reconhecida (mediana PRE {med})"
                continue
            if factor != 1:
                curves = {k: [(dc, du, v * factor) for dc, du, v in pts] for k, pts in curves.items()}
            print(f"[INFO] TaxaSwap {d}: fator de escala {factor}; PRE 1º vértice {curves['PRE'][0]}; DIC 1º vértice {(curves.get('DIC') or [None])[0]}")
            return {k: [(du, v) for _, du, v in pts if du > 0] for k, pts in curves.items()}
        except Exception as e:
            last = str(e)
    print(f"[AVISO] TaxaSwap B3 {d}: {last}")
    return {}


fetch_taxa_swap.logged = False
