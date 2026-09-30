"""
Debêntures no mercado secundário (ANBIMA)
-----------------------------------------
Baixa o arquivo diário de taxas indicativas de debêntures da ANBIMA, filtra os
papéis dos emissores acompanhados (Simpar, JSL, Movida, Vamos, Automob,
Localiza, Randoncorp, Frasle, Armac, Priner) e mantém o histórico dia a dia em
alerts/debentures.json, que alimenta a aba "Crédito" do painel.

Na primeira execução, busca também os últimos ~2 meses para já ter histórico.

Uso:
  python debentures_anbima.py
  python debentures_anbima.py --dias 60   # tenta preencher até 60 dias para trás
"""

import argparse
import json
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from alerta_acoes import BRT, HEADERS
from curvas_anbima import fetch_di_pre, fetch_titulos, swap_ipca
from negocios_snd import fetch_trades

OUT_DIR = Path(__file__).parent / "alerts"
DEB_FILE = OUT_DIR / "debentures.json"
URL = "https://www.anbima.com.br/informacoes/merc-sec-debentures/arqs/db{d:%y%m%d}.txt"
KEEP_DAYS = 400
FAVORITES = ["VAMO33", "VAMO34", "VAMO19"]

# emissor (nome no arquivo, sem acento e em maiúsculas) -> ticker da ação do grupo
ISSUERS = [
    (r"\bSIMPAR\b", "SIMH3", "Simpar"),
    (r"\bJSL\b", "JSLG3", "JSL"),
    (r"\bMOVIDA\b", "MOVI3", "Movida"),
    (r"\bVAMOS\b", "VAMO3", "Vamos"),
    (r"\bAUTOMOB\b", "AMOB3", "Automob"),
    (r"\bLOCALIZA\b", "RENT3", "Localiza"),
    (r"\bRANDON", "RAPT4", "Randoncorp"),
    (r"\bFRAS.?LE\b|\bFRASLE\b", "FRAS3", "Frasle"),
    (r"\bARMAC\b", "ARML3", "Armac"),
    (r"\bPRINER\b", "PRNR3", "Priner"),
]

CODE_RE = re.compile(r"^[A-Z]{3,5}[A-Z0-9]?\d{1,2}$")


def norm(s):
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).upper().strip()


def num(s):
    s = (s or "").strip()
    if not s or s in {"--", "-", "N/D"}:
        return None
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def parse_file(text):
    """Lê o txt da ANBIMA (campos separados por '@'). Devolve lista de papéis."""
    cols = None
    section = None
    rows = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("@")]
        if len(parts) == 1:
            t = norm(parts[0])
            if t and re.fullmatch(r"[A-Z_ ]{3,40}", t):
                section = t  # ex.: DI_PERCENTUAL, DI_SPREAD, IPCA_SPREAD
            continue
        head = [norm(p) for p in parts]
        if head and head[0].startswith("COD"):
            cols = head
            continue
        if not CODE_RE.match(parts[0]):
            continue

        def col(*names, default=None):
            if cols:
                for n in names:
                    for i, h in enumerate(cols):
                        if h.startswith(n) and i < len(parts):
                            return parts[i]
            return parts[default] if default is not None and default < len(parts) else ""

        rows.append({
            "code": parts[0],
            "name": col("NOME", default=1),
            "maturity": col("REPAC", "VENC", default=2),
            "index": col("INDICE", default=3) or section or "",
            "section": section,
            "rate": num(col("TAXA INDICATIVA", default=6)),
            "rateMin": num(col("INTERVALO INDICATIVO MIN", default=8)),
            "rateMax": num(col("INTERVALO INDICATIVO MAX", default=9)),
            "pu": num(col("PU", default=10)),
            "pctPar": num(col("% PU PAR", default=11)),
            "duration": num(col("DURATION", default=12)),
            "ntnbRef": col("REFERENCIA NTN-B", default=14),
        })
    return rows


def fetch_day(session, d):
    r = session.get(URL.format(d=d), timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    text = r.content.decode("latin-1")
    rows = parse_file(text)
    if not rows:
        print(f"[AVISO] {d}: arquivo sem papéis reconhecidos. Início do arquivo:\n{text[:600]}")
    return rows


def group_of(row):
    n = norm(row["name"])
    for pat, ticker, label in ISSUERS:
        if re.search(pat, n):
            return ticker, label
    return None, None


def is_ipca(p):
    return (p.get("index") or "").strip().upper().startswith("IPCA")


def business_days_back(n):
    d = datetime.now(BRT).date()
    out = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=45, help="quantos dias úteis para trás tentar preencher")
    args = ap.parse_args()
    OUT_DIR.mkdir(exist_ok=True)

    db = {"papers": {}, "dates": []}
    if DEB_FILE.exists():
        try:
            old = json.loads(DEB_FILE.read_text())
            db["papers"] = {p["code"]: p for p in old.get("papers", [])}
            db["dates"] = old.get("dates", [])
            db["curves"] = old.get("curves", {})
            db["tradeDays"] = old.get("tradeDays", [])
        except json.JSONDecodeError:
            pass
    have = set(db["dates"])

    session = requests.Session()
    session.headers.update({**HEADERS, "Accept": "text/plain,*/*"})

    # na primeira vez preenche o histórico; depois só os dias que faltam
    days = business_days_back(args.dias if len(have) < 5 else 7)
    fetched, errors = 0, 0
    for d in sorted(days):
        iso = d.isoformat()
        if iso in have:
            continue
        try:
            rows = fetch_day(session, d)
        except Exception as e:
            errors += 1
            print(f"[ERRO] {d}: {e}")
            continue
        if rows is None:
            continue  # feriado ou arquivo ainda não publicado
        fetched += 1
        n_match = 0
        for row in rows:
            ticker, label = group_of(row)
            if not ticker and row["code"] not in FAVORITES:
                continue
            n_match += 1
            p = db["papers"].setdefault(row["code"], {"code": row["code"], "series": []})
            p.update({k: row[k] for k in ("name", "maturity", "index", "section", "ntnbRef")})
            p["ticker"], p["issuer"] = ticker, label or row["name"]
            p["series"] = [s for s in p["series"] if s[0] != iso]
            p["series"].append([iso, row["rate"], row["pu"], row["duration"], row["rateMin"], row["rateMax"]])
            p["series"].sort()
        have.add(iso)
        print(f"[INFO] {d}: {len(rows)} papéis no arquivo, {n_match} dos emissores acompanhados.")
        if n_match == 0 and rows:  # noqa
            print("[AVISO] Nenhum emissor reconhecido. Exemplos de nomes:", sorted({r['name'] for r in rows})[:15])

    if not have:
        print("[ERRO] Nenhum arquivo da ANBIMA foi obtido.")
        sys.exit(1)

    # negócios do SND: volume, número de negócios e PU médio por papel e dia.
    # Também inclui papéis dos emissores que não têm taxa indicativa na ANBIMA.
    traded_days = set(db.get("tradeDays", []))
    for d in sorted(business_days_back(args.dias if len(traded_days) < 5 else 7)):
        iso = d.isoformat()
        if iso in traded_days and iso != sorted(have)[-1]:
            continue
        try:
            trades = fetch_trades(session, d)
        except Exception as e:
            print(f"[ERRO] negócios SND {iso}: {e}")
            continue
        if not trades:
            continue
        n = 0
        for t in trades:
            ticker, label = group_of({"name": t["issuer"]})
            if not ticker and t["code"] not in FAVORITES:
                continue
            p = db["papers"].setdefault(t["code"], {"code": t["code"], "series": [], "name": t["issuer"],
                                                   "issuer": label or t["issuer"], "ticker": ticker, "index": "", "maturity": ""})
            p.setdefault("trades", [])
            p["trades"] = [x for x in p["trades"] if x[0] != iso]
            p["trades"].append([iso, t["qty"], t["deals"], t["puMin"], t["puAvg"], t["puMax"], t["pctCurve"]])
            p["trades"].sort()
            p["isin"] = t["isin"]
            n += 1
        traded_days.add(iso)
        print(f"[INFO] negócios {iso}: {len(trades)} linhas no SND, {n} dos emissores acompanhados.")
    db["tradeDays"] = sorted(traded_days)

    # IPCA+: taxa trocada em NTN-B + e CDI + (ambas em %), posições 6 e 7 da série
    curves = db.get("curves", {})
    need = sorted({s[0] for p in db["papers"].values() if is_ipca(p)
                   for s in p["series"] if len(s) < 8 or s[6] is None})
    for iso in need[-60:]:
        d = date.fromisoformat(iso)
        try:
            tit = fetch_titulos(session, d)
        except Exception as e:
            print(f"[ERRO] títulos públicos {iso}: {e}")
            tit = None
        try:
            di = fetch_di_pre(session, d)
        except Exception as e:
            print(f"[ERRO] DI x Pré {iso}: {e}")
            di = []
        if not tit:
            continue
        curves[iso] = {"ntnb": tit["ntnb"], "di1y": next((t for dc, t in di if dc >= 365), None) if di else None}
        n = 0
        for p in db["papers"].values():
            if not is_ipca(p):
                continue
            for srow in p["series"]:
                if srow[0] != iso:
                    continue
                while len(srow) < 8:
                    srow.append(None)
                sp, cdi = swap_ipca(srow[1], srow[3], p.get("ntnbRef"), tit, di)
                srow[6] = round(sp, 4) if sp is not None else None
                srow[7] = round(cdi, 4) if cdi is not None else None
                n += srow[6] is not None
        print(f"[INFO] {iso}: {len(tit['ntnb'])} NTN-B, {len(tit['pre'])} pré, DI x Pré {len(di)} vértices; {n} papéis IPCA+ trocados.")

    # favoritos sempre aparecem, mesmo sem taxa ANBIMA nem negócio no período
    for f in FAVORITES:
        db["papers"].setdefault(f, {"code": f, "series": [], "trades": [], "name": "", "index": "", "maturity": "",
                                    "issuer": next((pp.get("issuer") for pp in db["papers"].values()
                                                    if pp["code"][:4] == f[:4] and pp.get("issuer")), f[:4]),
                                    "ticker": next((pp.get("ticker") for pp in db["papers"].values()
                                                    if pp["code"][:4] == f[:4] and pp.get("ticker")), None)})

    cutoff = (datetime.now(BRT).date() - timedelta(days=KEEP_DAYS)).isoformat()
    papers = []
    for p in db["papers"].values():
        p["series"] = [s for s in p["series"] if s[0] >= cutoff]
        p["trades"] = [t for t in p.get("trades", []) if t[0] >= cutoff]
        p["anbima"] = bool(p["series"])
        if p["series"] or p["trades"] or p["code"] in FAVORITES:
            papers.append(p)
    papers.sort(key=lambda p: (p.get("issuer") or "", p["code"]))
    dates = sorted(d for d in have if d >= cutoff)

    DEB_FILE.write_text(json.dumps({
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "ANBIMA - taxas indicativas de debêntures",
        "lastDate": dates[-1] if dates else None,
        "dates": dates,
        "favoritesDefault": FAVORITES,
        "curves": {k: v for k, v in curves.items() if k >= cutoff},
        "tradeDays": sorted(d for d in db.get("tradeDays", []) if d >= cutoff),
        "papers": papers,
    }, ensure_ascii=False))
    print(f"[INFO] {len(papers)} papéis salvos; {fetched} arquivo(s) novo(s); último dia {dates[-1] if dates else '-'}.")
    for f in FAVORITES:
        p = db["papers"].get(f)
        last = p["series"][-1] if p else None
        print(f"[INFO] favorito {f}: {'sem dados' if not last else f'{last[0]} taxa {last[1]} PU {last[2]}'}")


if __name__ == "__main__":
    main()
