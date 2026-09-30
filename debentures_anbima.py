"""
Debêntures no mercado secundário (ANBIMA)
-----------------------------------------
Baixa o arquivo diário de taxas indicativas de debêntures da ANBIMA, filtra os
papéis dos emissores acompanhados (Simpar, JSL, Movida, Vamos, Automob,
Localiza, Randoncorp, Frasle, Armac, Priner, Tupy) e mantém o histórico dia a dia em
alerts/debentures.json, que alimenta a aba "Crédito" do painel.

Na primeira execução, busca também os últimos ~2 meses para já ter histórico.

Uso:
  python debentures_anbima.py
  python debentures_anbima.py --dias 60   # tenta preencher até 60 dias para trás
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from alerta_acoes import BRT, HEADERS
from curva_b3 import fetch_taxa_swap
from curvas_anbima import fetch_di_pre, fetch_ettj, fetch_titulos, interp, swap_ipca
from negocios_snd import fetch_agenda, fetch_details, fetch_pu_historico, fetch_registered, fetch_trades
from alerta_acoes import DASHBOARD_URL, send_email

OUT_DIR = Path(__file__).parent / "alerts"
DEB_FILE = OUT_DIR / "debentures.json"
URL = "https://www.anbima.com.br/informacoes/merc-sec-debentures/arqs/db{d:%y%m%d}.txt"
KEEP_DAYS = 400
FAVORITES = ["VAMO33", "VAMO34", "VAMO19"]
B3_VERSION = 2  # mude para forçar o recálculo das curvas da B3 já gravadas

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
    (r"\bTUPY\b", "TUPY3", "Tupy"),
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


def send_new_issues(codes, papers):
    from email_layout import MUTED, data_table, button, page, esc
    rows = [[f"<b>{esc(c)}</b>", esc(papers.get(c, {}).get("issuer") or ""),
             f'<span style="font-size:12px;color:{MUTED}">'
             + esc(" · ".join(f"{k}: {v}" for k, v in list((papers.get(c, {}).get("details") or {}).items())[:6]) or "ficha ainda não disponível")
             + "</span>"] for c in codes]
    html_body = page("NOVA EMISSÃO DE DEBÊNTURE", f"{len(codes)} papel(éis) novo(s) dos emissores acompanhados",
                     "Detectado na lista de emissões registradas do SND",
                     data_table(["Papel", "Emissor", "Ficha"], rows, ["left", "left", "left"]) + button(DASHBOARD_URL, "Abrir aba Dívida"),
                     "Aviso automático: o papel apareceu hoje na lista de debêntures registradas do SND (debentures.com.br).")
    text = "Nova emissão de debênture: " + ", ".join(codes) + f"\nPainel: {DASHBOARD_URL}"
    send_email(f"[Crédito] Nova emissão: {', '.join(codes)}", text, html_body)
    print("[INFO] e-mail de nova emissão enviado.")


PANEL_FILE = OUT_DIR / "debentures_painel.json"
PANEL_LIMIT = 250_000  # o banco do painel aceita até 256 KB por documento


def _r(v, n):
    return round(v, n) if isinstance(v, float) else v


def write_panel_file():
    """Versão enxuta de debentures.json para o painel: sem o histórico de curvas, com números arredondados
    e, se ainda passar do limite, menos dias de negócios e de PU da curva."""
    full = json.loads(DEB_FILE.read_text())
    for keep_trades, keep_pu in ((60, 60), (40, 40), (25, 25), (15, 15)):
        papers = []
        for p in full["papers"]:
            q = {k: p[k] for k in ("code", "name", "issuer", "ticker", "index", "section", "maturity", "ntnbRef", "anbima", "status")
                 if k in p}
            q["series"] = [[s[0]] + [_r(x, 4) for x in s[1:]] for s in p.get("series", [])]
            q["trades"] = [[t[0]] + [_r(x, 2) for x in t[1:]] for t in p.get("trades", [])][-keep_trades:]
            q["puCurve"] = [[x[0], _r(x[1], 2)] for x in p.get("puCurve", [])][-keep_pu:]
            if p.get("details"):
                q["details"] = p["details"]
            if p.get("agenda"):
                q["agenda"] = p["agenda"]
            papers.append(q)
        cl = full.get("curveLatest") or {}
        panel = {k: full.get(k) for k in ("updatedAt", "source", "lastDate", "favoritesDefault", "newIssues")}
        panel["papers"] = papers
        panel["curveLatest"] = {**cl, "b3": {k: [[du, _r(v, 4)] for du, v in pts] for k, pts in (cl.get("b3") or {}).items()}}
        text = json.dumps(panel, ensure_ascii=False, separators=(",", ":"))
        if len(text.encode()) <= PANEL_LIMIT:
            break
    PANEL_FILE.write_text(text)
    print(f"[INFO] painel: {len(text.encode()) // 1024} KB ({keep_trades} dias de negócios por papel).")


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
            db["curveLatestOld"] = old.get("curveLatest", {})
            db["tradeDays"] = old.get("tradeDays", [])
            db["knownCodes"] = old.get("knownCodes", [])
            db["newIssues"] = old.get("newIssues", [])
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
                   for s in p["series"] if len(s) < 8 or s[6] is None or s[7] is None
                   or curves.get(s[0], {}).get("b3v") != B3_VERSION})
    for iso in need[-60:]:
        d = date.fromisoformat(iso)
        try:
            tit = fetch_titulos(session, d)
        except Exception as e:
            print(f"[ERRO] títulos públicos {iso}: {e}")
            tit = None
        di = []  # a curva DI x Pré da B3 saiu da página antiga; usa a ETTJ prefixada da ANBIMA
        try:
            ettj = fetch_ettj(session, d)
        except Exception as e:
            print(f"[ERRO] ETTJ {iso}: {e}")
            ettj = []
        if not tit:
            continue
        try:
            b3 = fetch_taxa_swap(session, d)
        except Exception as e:
            print(f"[AVISO] TaxaSwap {iso}: {e}")
            b3 = {}
        if b3:
            print(f"[INFO] B3 {iso}: curvas {sorted(b3)}; PRE 252du={interp(b3.get('PRE', []), 252)} 756du={interp(b3.get('PRE', []), 756)}; "
                  f"DIC 252du={interp(b3.get('DIC', []), 252)} 756du={interp(b3.get('DIC', []), 756)}")
        curves[iso] = {"ntnb": tit["ntnb"], "ettj": ettj, "b3": {k: b3[k] for k in ("PRE", "DIC") if k in b3}, "b3v": B3_VERSION}
        n = 0
        for p in db["papers"].values():
            if not is_ipca(p):
                continue
            for srow in p["series"]:
                if srow[0] != iso:
                    continue
                while len(srow) < 8:
                    srow.append(None)
                sp, cdi = swap_ipca(srow[1], srow[3], p.get("ntnbRef"), tit, di, ettj, curves[iso]["b3"])
                srow[6] = round(sp, 4) if sp is not None else None
                srow[7] = round(cdi, 4) if cdi is not None else None
                n += srow[6] is not None
        print(f"[INFO] {iso}: {len(tit['ntnb'])} NTN-B, {len(tit['pre'])} pré, ETTJ {len(ettj)} vértices; {n} papéis IPCA+ trocados.")

    # curva NTN-B/ETTJ: tenta o dia de hoje e os últimos dias úteis; só troca a curva
    # quando vem completa (se a ANBIMA ainda não publicou, fica a última boa)
    for d in sorted(business_days_back(4)):
        iso = d.isoformat()
        cur = curves.get(iso) or {}
        if cur.get("ntnb") and cur.get("ettj") and cur.get("b3v") == B3_VERSION and (cur.get("b3") or {}).get("PRE"):
            continue
        try:
            tit = fetch_titulos(session, d)
            ettj = fetch_ettj(session, d) if tit and tit.get("ntnb") else []
        except Exception as e:
            print(f"[AVISO] curva {iso}: {e}")
            continue
        if tit and tit.get("ntnb") and ettj:
            b3 = (curves.get(iso) or {}).get("b3") or {}
            if not b3 or (curves.get(iso) or {}).get("b3v") != B3_VERSION:
                try:
                    b3 = {k: v for k, v in fetch_taxa_swap(session, d).items() if k in ("PRE", "DIC")}
                except Exception as e:
                    print(f"[AVISO] TaxaSwap {iso}: {e}")
            curves[iso] = {"ntnb": tit["ntnb"], "ettj": ettj, "b3": b3, "b3v": B3_VERSION}
            print(f"[INFO] curva {iso}: {len(tit['ntnb'])} NTN-B e {len(ettj)} vértices ETTJ.")
        else:
            print(f"[INFO] curva {iso}: ainda não publicada pela ANBIMA.")
    good = sorted(k for k, v in curves.items() if v.get("ntnb") and v.get("ettj"))
    curve_day = good[-1] if good else None
    prev_day = good[-2] if len(good) > 1 else None

    # todos os papéis registrados dos emissores (SND), mesmo sem ANBIMA nem negócio
    try:
        regs = fetch_registered(session)
    except Exception as e:
        print(f"[ERRO] lista de emissões SND: {e}")
        regs = []
    n_new = 0
    for rg in regs:
        ticker, label = group_of({"name": rg["issuer"]})
        if not ticker:
            continue
        if rg["code"] not in db["papers"]:
            n_new += 1
        pp = db["papers"].setdefault(rg["code"], {"code": rg["code"], "series": [], "trades": [], "index": "", "maturity": ""})
        pp.setdefault("name", rg["issuer"])
        pp["ticker"], pp["issuer"] = ticker, label
        pp["status"] = rg["status"]
    print(f"[INFO] SND: {len(regs)} emissões registradas; {n_new} papéis dos emissores sem ANBIMA/negócio adicionados.")

    # nova emissão: papel dos emissores que não estava na lista conhecida
    ours = sorted({rg["code"] for rg in regs if group_of({"name": rg["issuer"]})[0]})
    known = set(db.get("knownCodes", []))
    fresh = [c for c in ours if c not in known] if known else []  # 1ª execução só grava a base
    today_iso = datetime.now(BRT).date().isoformat()
    if fresh:
        for c in fresh:
            pp = db["papers"].get(c, {})
            db["newIssues"].append({"code": c, "issuer": pp.get("issuer"), "ticker": pp.get("ticker"), "detectedAt": today_iso})
        print(f"[INFO] NOVAS EMISSÕES: {', '.join(fresh)}")
    db["knownCodes"] = sorted(known | set(ours))
    db["newIssues"] = [x for x in db["newIssues"] if x["detectedAt"] >= (datetime.now(BRT).date() - timedelta(days=30)).isoformat()]

    # ficha (emissão, vencimento, valor nominal, remuneração) e agenda de juros/amortizações
    n_det = 0
    # ficha/agenda do SND pausada: o endereço atual responde erro 500 para todos os papéis
    for pp in (db["papers"].values() if os.environ.get("SND_FICHA") == "1" else []):
        if not pp.get("ticker"):
            continue
        refresh_agenda = pp.get("agendaAt", "") < (datetime.now(BRT).date() - timedelta(days=7)).isoformat()
        if pp.get("details") and not refresh_agenda:
            continue
        try:
            if not pp.get("details"):
                pp["details"] = fetch_details(session, pp["code"])
            pp["agenda"] = fetch_agenda(session, pp["code"])
            pp["agendaAt"] = today_iso
            n_det += 1
        except Exception as e:
            print(f"[AVISO] ficha/agenda {pp['code']}: {e}")
    print(f"[INFO] fichas/agendas atualizadas: {n_det}")
    sample = db["papers"].get("VAMO33", {})
    print("[INFO] exemplo ficha VAMO33:", dict(list((sample.get("details") or {}).items())[:25]))
    print("[INFO] exemplo agenda VAMO33:", (sample.get("agenda") or [])[:8])

    if fresh and os.environ.get("SMTP_HOST"):
        try:
            send_new_issues(fresh, db["papers"])
        except Exception as e:
            print(f"[ERRO] e-mail de nova emissão: {e}")

    # PU da curva (SND) para papéis sem taxa ANBIMA: dá um gráfico mesmo sem mercado
    start = (datetime.now(BRT).date() - timedelta(days=90))
    for pp in db["papers"].values():
        if pp.get("series") and any(x[1] is not None for x in pp["series"]):
            continue
        if not pp.get("ticker") or (pp.get("status") and not pp["status"].upper().startswith("REG")):
            continue
        try:
            hist = fetch_pu_historico(session, pp["code"], start, datetime.now(BRT).date())
        except Exception as e:
            print(f"[AVISO] PU histórico {pp['code']}: {e}")
            continue
        pp["puCurve"] = hist[-90:]

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
        if p["series"] or p["trades"] or p.get("puCurve") or p.get("status") or p["code"] in FAVORITES:
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
        "curveLatest": ({"date": curve_day, **curves[curve_day],
                         "prevDate": prev_day, "prevNtnb": curves[prev_day]["ntnb"] if prev_day else []}
                        if curve_day else (old_latest if (old_latest := (db.get("curveLatestOld") or {})) else {})),
        "tradeDays": sorted(d for d in db.get("tradeDays", []) if d >= cutoff),
        "knownCodes": db.get("knownCodes", []),
        "newIssues": db.get("newIssues", []),
        "papers": papers,
    }, ensure_ascii=False))
    write_panel_file()
    print(f"[INFO] {len(papers)} papéis salvos; {fetched} arquivo(s) novo(s); último dia {dates[-1] if dates else '-'}.")
    for f in FAVORITES:
        p = db["papers"].get(f)
        last = p["series"][-1] if p and p["series"] else None
        ntr = len(p.get("trades", [])) if p else 0
        print(f"[INFO] favorito {f}: {'sem taxa ANBIMA' if not last else f'{last[0]} taxa {last[1]} PU {last[2]}'}; {ntr} dia(s) com negócio")


if __name__ == "__main__":
    main()
