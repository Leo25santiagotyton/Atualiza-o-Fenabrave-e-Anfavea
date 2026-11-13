"""
Implementos rodoviários: ANFIR (emplacamentos) e Comex Stat (antigo AliceWeb) para reboques e semirreboques
--------------------------------------------------------------------------------------------------------
ANFIR: a página "Dados do Setor" publica um PDF por mês ("Desempenho do setor - Janeiro a <mês> de <ano>")
com o emplacamento ACUMULADO do ano por família de reboques e semirreboques (linha pesada) e de carrocerias
sobre chassis (linha leve), o total do mercado interno e as exportações, sempre contra o mesmo período do
ano anterior. O mês isolado sai da diferença entre dois acumulados seguidos do mesmo ano.

Comex Stat (comexstat.mdic.gov.br, que substituiu o AliceWeb): exportação e importação mensal, em US$ FOB
e quilos, das NCMs de reboques e semirreboques (8716.20, 8716.31, 8716.39 e 8716.40), pela API pública.

Grava alerts/implementos.json, que entra na aba Monitoramento (monitoramento.py).

Uso:
  python implementos.py            # atualiza (só baixa PDFs da ANFIR que ainda não leu)
  python implementos.py --refazer  # relê todos os PDFs da ANFIR desde ANO_INI
"""

import argparse
import io
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pdfplumber
import requests
from bs4 import BeautifulSoup

from monitor import BROWSER_HEADERS

OUT = Path(__file__).parent / "alerts" / "implementos.json"
BRT = timezone(timedelta(hours=-3))
ANFIR_PAGE = "https://anfir.org.br/dados-do-setor.php"
COMEX_API = "https://api-comexstat.mdic.gov.br"
ANO_INI = 2023
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]
NCMS = {"87162000": "Agrícolas (autocarregáveis etc.)", "87163100": "Reboques-cisterna (tanque)",
        "87163900": "Outros p/ transporte de mercadorias", "87164000": "Outros reboques e semirreboques"}
SECOES = {"REBOQUES E SEMIRREBOQUES": "reb", "CARROCERIAS SOBRE CHASSIS": "carr",
          "TOTAL GERAL MERCADO INTERNO": "tot", "EXPORTAÇÕES": "exp", "MERCADO EXTERNO": "exp"}


def _num(s):
    return int(s.replace(".", "")) if s not in (None, "") else None


def _session():
    s = requests.Session()
    s.headers.update(BROWSER_HEADERS)
    return s


# ---------------------------------------------------------------- ANFIR
def periodo_anfir(titulo):
    """'Desempenho do setor - Janeiro a Setembro de 2026' -> (2026, 9)."""
    t = titulo.lower()
    m = re.search(r"(\d{4})", t)
    if not m:
        return None
    ano = int(m.group(1))
    if "trimestre" in t:
        return ano, 3
    if "quadrimestre" in t:
        return ano, 4
    m2 = re.search(r"janeiro\s+(?:a|e)\s+(\w+)", t)
    if m2 and m2.group(1) in MESES:
        return ano, MESES.index(m2.group(1)) + 1
    if re.search(r"janeiro\s+de\s+\d{4}", t):
        return ano, 1
    return None


def lista_anfir(s):
    r = s.get(ANFIR_PAGE, timeout=40)
    r.raise_for_status()
    out = {}
    for a in BeautifulSoup(r.text, "html.parser").find_all("a", href=True):
        t = " ".join(a.get_text(" ").split())
        if not re.search(r"desempenho d[eo] setor", t, re.I) or ".pdf" not in a["href"].lower():
            continue
        p = periodo_anfir(t)
        if p and p[0] >= ANO_INI:
            out[f"{p[0]}-{p[1]:02d}"] = {"titulo": t, "url": requests.compat.urljoin(r.url, a["href"].strip())}
    return out


def parse_anfir(texto):
    """Primeira página do PDF: famílias com acumulado do ano anterior e do ano, por seção."""
    d = {"reb": {}, "carr": {}, "reb_aa": {}, "carr_aa": {}}
    sec = None
    for ln in texto.splitlines():
        ln = " ".join(ln.split())
        if ln.upper() in SECOES:
            sec = SECOES[ln.upper()]
            continue
        m = re.match(r"^(.+?)\s+(\d{1,3}(?:\.\d{3})*)\s+(\d{1,3}(?:\.\d{3})*)\s+(-?\d+(?:,\d+)?)$", ln)
        if not m or sec is None:
            continue
        nome, ant, atu = m.group(1).strip(), _num(m.group(2)), _num(m.group(3))
        if sec in ("reb", "carr"):
            if nome.upper() == "TOTAL":
                d[sec + "_total"], d[sec + "_total_aa"] = atu, ant
            else:
                d[sec][nome.title()], d[sec + "_aa"][nome.title()] = atu, ant
        elif sec == "tot" and nome.upper() == "TOTAL":
            d["total"], d["total_aa"] = atu, ant
        elif sec == "exp" and "EXPORTA" in nome.upper():
            d["exp"], d["exp_aa"] = atu, ant
    return d if d.get("reb_total") and d.get("carr_total") else None


def anfir(base, refazer=False):
    s = _session()
    lista = lista_anfir(s)
    lidos = {} if refazer else (base.get("acum") or {})
    for k, v in sorted(lista.items()):
        if k in lidos and lidos[k].get("url") == v["url"]:
            continue
        try:
            r = s.get(v["url"], timeout=60)
            r.raise_for_status()
            with pdfplumber.open(io.BytesIO(r.content)) as pdf:
                d = parse_anfir(pdf.pages[0].extract_text() or "")
        except Exception as exc:  # noqa: BLE001
            print(f"[AVISO] ANFIR {k}: {exc}")
            continue
        if not d:
            print(f"[AVISO] ANFIR {k}: não li a tabela de {v['url']}")
            continue
        lidos[k] = {**d, "url": v["url"], "titulo": v["titulo"]}
        print(f"[INFO] ANFIR {k}: reboques {d['reb_total']}, carrocerias {d['carr_total']}, total {d.get('total')}")
    return lidos


def meses_anfir(acum):
    """Mês isolado = acumulado do mês - acumulado do mês anterior (mesmo ano)."""
    out = []
    for k in sorted(acum):
        a, m = int(k[:4]), int(k[5:])
        cur = acum[k]
        prev = acum.get(f"{a}-{m - 1:02d}") if m > 1 else {}
        if prev is None:
            continue
        sub = lambda c, p: (c - p) if c is not None and p is not None else None  # noqa: E731
        out.append({"mes": k,
                    "reb": sub(cur.get("reb_total"), prev.get("reb_total", 0)),
                    "carr": sub(cur.get("carr_total"), prev.get("carr_total", 0)),
                    "total": sub(cur.get("total"), prev.get("total", 0)),
                    "exp": sub(cur.get("exp"), prev.get("exp", 0)),
                    "familias": {f: sub(v, (prev.get("reb") or {}).get(f, 0) if m > 1 else 0)
                                 for f, v in (cur.get("reb") or {}).items()}})
    return out


# ---------------------------------------------------------------- Comex Stat
def comex():
    agora = datetime.now(BRT)
    upd = requests.get(COMEX_API + "/general/dates/updated", timeout=40).json()["data"]
    meses = {}
    for flow in ("export", "import"):
        body = {"flow": flow, "monthDetail": True,
                "period": {"from": f"{ANO_INI}-01", "to": f"{agora.year}-12"},
                "filters": [{"filter": "ncm", "values": list(NCMS)}],
                "details": ["ncm"], "metrics": ["metricFOB", "metricKG"]}
        r = requests.post(COMEX_API + "/general", json=body, timeout=90, headers={"Accept": "application/json"})
        r.raise_for_status()
        for x in r.json()["data"]["list"]:
            k = f"{x['year']}-{int(x['monthNumber']):02d}"
            e = meses.setdefault(k, {"mes": k, "exp_fob": 0, "exp_kg": 0, "imp_fob": 0, "imp_kg": 0, "ncm": {}})
            p = "exp" if flow == "export" else "imp"
            fob, kg = float(x.get("metricFOB") or 0), float(x.get("metricKG") or 0)
            e[p + "_fob"] += fob
            e[p + "_kg"] += kg
            n = e["ncm"].setdefault(x["coNcm"], {"exp_fob": 0, "imp_fob": 0})
            n[p + "_fob"] += fob
    print(f"[INFO] Comex Stat: {len(meses)} meses; base atualizada em {upd.get('updated')} (até {upd.get('monthNumber')}/{upd.get('year')}).")
    return {"atualizado": upd.get("updated"), "ultimo": f"{upd.get('year')}-{int(upd.get('monthNumber')):02d}",
            "ncms": NCMS, "meses": [meses[k] for k in sorted(meses)]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refazer", action="store_true")
    args = ap.parse_args()
    base = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    out = dict(base)
    erros = []
    try:
        acum = anfir(base.get("anfir") or {}, args.refazer)
        ult = max(acum) if acum else None
        out["anfir"] = {"acum": acum, "ultimo": ult, "titulo": acum[ult]["titulo"] if ult else None,
                        "url": acum[ult]["url"] if ult else None, "meses": meses_anfir(acum), "fonte": ANFIR_PAGE}
        if ult and ult != (base.get("anfir") or {}).get("ultimo"):
            out["anfir"]["novo_em"] = datetime.now(BRT).isoformat(timespec="seconds")
        else:
            out["anfir"]["novo_em"] = (base.get("anfir") or {}).get("novo_em")
    except Exception as exc:  # noqa: BLE001
        erros.append(f"ANFIR: {exc}")
    try:
        out["comex"] = comex()
    except Exception as exc:  # noqa: BLE001
        erros.append(f"Comex Stat: {exc}")
    out["gerado_em"] = datetime.now(BRT).isoformat(timespec="seconds")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for e in erros:
        print(f"[ERRO] {e}", file=sys.stderr)
    if erros and not (out.get("anfir") or out.get("comex")):
        sys.exit(1)


if __name__ == "__main__":
    main()
