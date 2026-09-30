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
import os
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from alerta_acoes import BRT, HEADERS
from curvas_anbima import fetch_di_pre, fetch_ettj, fetch_titulos, swap_ipca
from negocios_snd import fetch_agenda, fetch_details, fetch_pu_historico, fetch_registered, fetch_trades
from alerta_acoes import DASHBOARD_URL, send_email

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


def send_new_issues(codes, papers):
    rows = "".join(
        f"<tr><td style='padding:6px 10px;border-bottom:1px solid #e2e6eb'><b>{c}</b></td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #e2e6eb'>{papers.get(c, {}).get('issuer') or ''}</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #e2e6eb;color:#5d6570;font-size:12px'>"
        + " · ".join(f"{k}: {v}" for k, v in list((papers.get(c, {}).get('details') or {}).items())[:6]) + "</td></tr>"
        for c in codes)
    html_body = f"""<!doctype html><html><body style="font-family:Roboto,Arial,sans-serif;background:#f5f7fa;margin:0">
  <div style="max-width:640px;margin:0 auto;padding:20px 12px">
    <div style="background:#0f1216;color:#fff;border-radius:12px 12px 0 0;padding:14px 18px">
      <div style="color:#f5a623;font-size:12px;font-weight:700;letter-spacing:.08em">NOVA EMISSÃO DE DEBÊNTURE</div>
      <div style="font-size:18px;margin-top:4px">{len(codes)} papel(éis) novo(s) dos emissores acompanhados</div></div>
    <div style="background:#fff;border:1px solid #e2e6eb;border-top:0;border-radius:0 0 12px 12px">
      <table style="width:100%;border-collapse:collapse;font-size:13px">{rows}</table>
      <div style="padding:14px 16px"><a href="{DASHBOARD_URL}" style="background:#1a5fd1;color:#fff;padding:8px 16px;border-radius:8px;text-decoration:none;font-size:13px">Abrir aba Dívida</a></div>
    </div></div></body></html>"""
    text = "Nova emissão de debênture: " + ", ".join(codes) + f"\nPainel: {DASHBOARD_URL}"
    send_email(f"[Crédito] Nova emissão: {', '.join(codes)}", text, html_body)
    print("[INFO] e-mail de nova emissão enviado.")


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
                   for s in p["series"] if len(s) < 8 or s[6] is None or s[7] is None})
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
        curves[iso] = {"ntnb": tit["ntnb"], "ettj": ettj}
        n = 0
        for p in db["papers"].values():
            if not is_ipca(p):
                continue
            for srow in p["series"]:
                if srow[0] != iso:
                    continue
                while len(srow) < 8:
                    srow.append(None)
                sp, cdi = swap_ipca(srow[1], srow[3], p.get("ntnbRef"), tit, di, ettj)
                srow[6] = round(sp, 4) if sp is not None else None
                srow[7] = round(cdi, 4) if cdi is not None else None
                n += srow[6] is not None
        print(f"[INFO] {iso}: {len(tit['ntnb'])} NTN-B, {len(tit['pre'])} pré, ETTJ {len(ettj)} vértices; {n} papéis IPCA+ trocados.")

    last_iso = sorted(have)[-1]
    if last_iso not in curves or not curves[last_iso].get("ettj"):
        try:
            d = date.fromisoformat(last_iso)
            tit = fetch_titulos(session, d)
            curves[last_iso] = {"ntnb": tit["ntnb"] if tit else [], "ettj": fetch_ettj(session, d)}
        except Exception as e:
            print(f"[ERRO] curva do último dia: {e}")

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
    for pp in db["papers"].values():
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
        "curveLatest": {"date": last_iso, **curves.get(last_iso, {})},
        "tradeDays": sorted(d for d in db.get("tradeDays", []) if d >= cutoff),
        "knownCodes": db.get("knownCodes", []),
        "newIssues": db.get("newIssues", []),
        "papers": papers,
    }, ensure_ascii=False))
    print(f"[INFO] {len(papers)} papéis salvos; {fetched} arquivo(s) novo(s); último dia {dates[-1] if dates else '-'}.")
    for f in FAVORITES:
        p = db["papers"].get(f)
        last = p["series"][-1] if p and p["series"] else None
        ntr = len(p.get("trades", [])) if p else 0
        print(f"[INFO] favorito {f}: {'sem taxa ANBIMA' if not last else f'{last[0]} taxa {last[1]} PU {last[2]}'}; {ntr} dia(s) com negócio")


if __name__ == "__main__":
    main()
