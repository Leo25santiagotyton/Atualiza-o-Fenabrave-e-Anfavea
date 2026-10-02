"""
Alerta de variação das ações B3
-------------------------------
Roda a cada 2 horas durante o pregão (via GitHub Actions). Busca as cotações
no Yahoo Finance e, se alguma ação estiver com alta ou queda de 2%, 4% ou 8%
(ou mais) no dia, envia um e-mail de lembrete.

Também grava alerts/prices.json com a foto dos preços, usada para atualizar o
dashboard publicado no claude.ai.

E-mail via as mesmas variáveis do monitor:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM, EMAIL_TO

Uso:
  python alerta_acoes.py                 # busca, grava a foto e envia se houver alerta
  python alerta_acoes.py --dry-run       # não envia; salva o e-mail em alerts/preview.html
  python alerta_acoes.py --demo --dry-run  # dados simulados, para ver o modelo do e-mail
  python alerta_acoes.py --no-email      # só atualiza a foto de preços do painel
"""

import argparse
import json
import math
import os
import random
import smtplib
import sys
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

TICKERS = [
    "MOVI3", "SIMH3", "VAMO3", "JSLG3", "AMOB3", "RAPT3",
    "RAPT4", "RENT3", "FRAS3", "ARML3", "PRNR3", "TUPY3",
]
LEVELS = [8, 4, 2]  # do maior para o menor
BRT = ZoneInfo("America/Sao_Paulo")
DASHBOARD_URL = "https://claude.ai/artifact/UHYqgM4PcixNRmxt7AFBhk"

OUT_DIR = Path(__file__).parent / "alerts"
PRICES_FILE = OUT_DIR / "prices.json"
STATE_FILE = OUT_DIR / "alert_state.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


# ---------------------------------------------------------------- dados
def fetch_chart(session, ticker, rng, interval):
    last_err = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            r = session.get(
                f"https://{host}/v8/finance/chart/{ticker}.SA",
                params={"range": rng, "interval": interval, "includePrePost": "false"},
                timeout=15,
            )
            r.raise_for_status()
            return r.json()["chart"]["result"][0]
        except Exception as e:
            last_err = e
    raise RuntimeError(f"{ticker} ({rng}): {last_err}")


def fetch_quote(session, ticker):
    day = fetch_chart(session, ticker, "1d", "5m")
    meta = day.get("meta", {})
    q = (day.get("indicators", {}).get("quote") or [{}])[0]
    ts = day.get("timestamp") or []
    points = [[t, round(c, 4)] for t, c in zip(ts, q.get("close") or []) if c is not None]
    opens = [o for o in (q.get("open") or []) if o is not None]

    def series(rng, interval):
        try:
            m = fetch_chart(session, ticker, rng, interval)
            mq = (m.get("indicators", {}).get("quote") or [{}])[0]
            return [[t, round(c, 2)] for t, c in zip(m.get("timestamp") or [], mq.get("close") or []) if c is not None]
        except Exception as e:
            print(f"[AVISO] {e}")
            return []

    # históricos para as abas do painel: 5 dias (15 min), 1 mês e 1 ano (diário)
    week = series("5d", "15m")
    month = series("1mo", "1d")
    year = series("1y", "1d")

    return {
        "symbol": ticker,
        "name": meta.get("longName") or meta.get("shortName") or ticker,
        "price": meta.get("regularMarketPrice") or (points[-1][1] if points else None),
        "previousClose": meta.get("previousClose") or meta.get("chartPreviousClose"),
        "open": opens[0] if opens else None,
        "dayHigh": meta.get("regularMarketDayHigh"),
        "dayLow": meta.get("regularMarketDayLow"),
        "volume": meta.get("regularMarketVolume"),
        "marketTime": meta.get("regularMarketTime"),
        "points": points,
        "week": week,
        "month": month,
        "year": year,
    }


FUND_FILE = OUT_DIR / "fundamentals.json"
FUND_MAX_AGE = 20 * 3600  # dados de balanço mudam pouco: atualiza no máximo ~1x por dia


def _raw(d, *keys):
    for k in keys:
        v = (d or {}).get(k)
        if isinstance(v, dict):
            v = v.get("raw")
        if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)):
            return v
    return None


def yahoo_crumb(session):
    """O quoteSummary do Yahoo pede um cookie de sessão e um 'crumb'."""
    nav = {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"}
    for url in ("https://fc.yahoo.com", "https://finance.yahoo.com/quote/VAMO3.SA"):
        try:
            session.get(url, timeout=15, allow_redirects=True, headers=nav)
        except Exception:
            pass
    for host in ("query2.finance.yahoo.com", "query1.finance.yahoo.com"):
        try:
            r = session.get(f"https://{host}/v1/test/getcrumb", timeout=15, headers={"Accept": "*/*"})
            if r.ok and r.text and "<" not in r.text:
                return r.text.strip()
        except Exception:
            pass
    return None


TS_TYPES = {  # campo nosso → séries do Yahoo (a primeira que vier com valor)
    "ebitda": ["trailingEBITDA", "trailingNormalizedEBITDA", "annualEBITDA"],
    "totalDebt": ["quarterlyTotalDebt", "annualTotalDebt"],
    "totalCash": ["quarterlyCashCashEquivalentsAndShortTermInvestments", "quarterlyCashAndCashEquivalents", "annualCashCashEquivalentsAndShortTermInvestments"],
    "shares": ["quarterlyOrdinarySharesNumber", "quarterlyShareIssued", "annualOrdinarySharesNumber"],
}


def fetch_timeseries(session, ticker):
    """Balanço e DRE pelo endpoint de séries de fundamentos do Yahoo (não pede crumb)."""
    types = sorted({t for v in TS_TYPES.values() for t in v})
    now = int(time.time())
    last = None
    for host in ("query2.finance.yahoo.com", "query1.finance.yahoo.com"):
        try:
            r = session.get(f"https://{host}/ws/fundamentals-timeseries/v1/finance/timeseries/{ticker}.SA",
                            params={"symbol": f"{ticker}.SA", "type": ",".join(types), "period1": now - 3 * 365 * 86400, "period2": now},
                            timeout=20)
            r.raise_for_status()
            series = {}
            for item in (r.json().get("timeseries") or {}).get("result") or []:
                for t in (item.get("meta") or {}).get("type") or []:
                    pts = [p for p in item.get(t) or [] if p and (p.get("reportedValue") or {}).get("raw") is not None]
                    if pts:
                        pts.sort(key=lambda p: p.get("asOfDate") or "")
                        series[t] = (pts[-1]["reportedValue"]["raw"], pts[-1].get("asOfDate"))
            out = {}
            for k, names in TS_TYPES.items():
                hit = next((series[n] for n in names if n in series), None)
                if hit:
                    out[k], out[k + "Date"] = hit
            if not out:
                raise RuntimeError("séries vazias")
            return out
        except Exception as e:
            last = e
    raise RuntimeError(f"séries {ticker}: {last}")


def fetch_fundamentals(session, ticker, crumb):
    """Ações, dívida, caixa e EBITDA (12 meses) do Yahoo Finance: séries de fundamentos e, se faltar algo, o quoteSummary."""
    ts = {}
    try:
        ts = fetch_timeseries(session, ticker)
    except Exception as e:
        print(f"[AVISO] {e}")
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if all(ts.get(k) is not None for k in ("ebitda", "totalDebt", "totalCash", "shares")):
        return {**ts, "at": stamp, "via": "timeseries"}
    try:
        qs = fetch_quotesummary(session, ticker, crumb)
    except Exception:
        if ts:
            return {**ts, "at": stamp, "via": "timeseries"}
        raise
    return {**qs, **{k: v for k, v in ts.items() if v is not None}, "via": "timeseries+quoteSummary" if ts else "quoteSummary"}


def fetch_quotesummary(session, ticker, crumb):
    """Ações, market cap, dívida, caixa e EBITDA (12 meses) pelo quoteSummary do Yahoo (pede cookie + crumb)."""
    params = {"modules": "price,defaultKeyStatistics,financialData,summaryDetail"}
    if crumb:
        params["crumb"] = crumb
    last = None
    for host in ("query2.finance.yahoo.com", "query1.finance.yahoo.com"):
        try:
            r = session.get(f"https://{host}/v10/finance/quoteSummary/{ticker}.SA", params=params, timeout=20)
            r.raise_for_status()
            res = (r.json().get("quoteSummary") or {}).get("result") or []
            if not res:
                raise RuntimeError("sem resultado")
            res = res[0]
            pr, ks, fd, sd = res.get("price"), res.get("defaultKeyStatistics"), res.get("financialData"), res.get("summaryDetail")
            return {
                "shares": _raw(ks, "impliedSharesOutstanding", "sharesOutstanding"),
                "sharesTicker": _raw(ks, "sharesOutstanding"),
                "marketCap": _raw(pr, "marketCap") or _raw(sd, "marketCap"),
                "ebitda": _raw(fd, "ebitda"),
                "totalDebt": _raw(fd, "totalDebt"),
                "totalCash": _raw(fd, "totalCash"),
                "enterpriseValue": _raw(ks, "enterpriseValue"),
                "evEbitdaYahoo": _raw(ks, "enterpriseToEbitda"),
                "currency": (pr or {}).get("currency") or "BRL",
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        except Exception as e:
            last = e
    raise RuntimeError(f"fundamentos {ticker}: {last}")


def load_fundamentals(session, tickers):
    cache = json.loads(FUND_FILE.read_text()) if FUND_FILE.exists() else {}
    stale = [t for t in tickers if not cache.get(t) or
             (datetime.now(timezone.utc) - datetime.fromisoformat(cache[t]["at"])).total_seconds() > FUND_MAX_AGE]
    if stale:
        crumb = yahoo_crumb(session)
        for t in stale:
            try:
                cache[t] = fetch_fundamentals(session, t, crumb)
            except Exception as e:
                print(f"[AVISO] {e}")
        FUND_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True))
        print(f"[INFO] fundamentos atualizados: {', '.join(t for t in stale if t in cache)}")
    return cache


# empresas com duas classes de ação: o Yahoo dá o total de ações da companhia, então o valor de mercado
# usa o preço da classe mais líquida e vale igual para as duas
COMPANY_PRICE = {"RAPT3": "RAPT4"}


def attach_fundamentals(q, f, prices=None):
    """Market cap pelo preço de agora; EV = market cap + dívida bruta − caixa; EV/EBITDA dos últimos 12 meses."""
    if not f:
        return
    ref = COMPANY_PRICE.get(q.get("symbol"))
    price = (prices or {}).get(ref) if ref else q.get("price")
    price = price or q.get("price")
    shares = f.get("shares")
    mcap = price * shares if price and shares else f.get("marketCap")
    ev = mcap + (f.get("totalDebt") or 0) - (f.get("totalCash") or 0) if mcap and f.get("totalDebt") is not None else f.get("enterpriseValue")
    q["fund"] = {
        "shares": shares, "marketCap": mcap, "totalDebt": f.get("totalDebt"), "totalCash": f.get("totalCash"),
        "netDebt": (f.get("totalDebt") - (f.get("totalCash") or 0)) if f.get("totalDebt") is not None else None,
        "ev": ev, "ebitda": f.get("ebitda"),
        "evEbitda": round(ev / f["ebitda"], 2) if ev and f.get("ebitda") and f["ebitda"] > 0 else None,
        "at": f.get("at"), "asOf": f.get("ebitdaDate") or f.get("totalDebtDate"), "source": "Yahoo Finance",
        "priceRef": ref,
    }


def demo_quote(ticker):
    rnd = random.Random(ticker + str(int(time.time() // 7200)))
    prev = round(rnd.uniform(2, 45), 2)
    pct = rnd.choice([rnd.uniform(-1.8, 1.8)] * 3 + [rnd.uniform(-10, 10)])
    now = int(time.time())
    p, points = prev, []
    for i in range(60):
        p += (prev * (1 + pct / 100) - p) / (60 - i) + rnd.gauss(0, prev * 0.002)
        points.append([now - (60 - i) * 300, round(p, 2)])
    price = round(prev * (1 + pct / 100), 2)
    return {
        "symbol": ticker, "name": f"{ticker} (simulado)", "price": price, "previousClose": prev,
        "open": points[0][1], "dayHigh": max(c for _, c in points), "dayLow": min(c for _, c in points),
        "volume": rnd.randint(500_000, 9_000_000), "marketTime": now, "points": points,
        "week": [[now - (130 - i) * 900, round(prev * (1 + rnd.gauss(0, 0.01)), 2)] for i in range(130)],
        "month": [[now - (22 - i) * 86400, round(prev * (1 + rnd.gauss(0, 0.03)), 2)] for i in range(22)],
        "year": [[now - (250 - i) * 86400, round(prev * (1 + 0.15 * math.sin(i / 30) + rnd.gauss(0, 0.02)), 2)] for i in range(250)],
    }


def day_change(q):
    if q.get("price") is None or not q.get("previousClose"):
        return None
    return (q["price"] - q["previousClose"]) / q["previousClose"] * 100


def level_of(pct):
    return next((l for l in LEVELS if abs(pct) >= l), 0)


# ---------------------------------------------------------------- e-mail
def br(v, casas=2):
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def build_email(hits, quotes, now, new_symbols):
    """Monta assunto, texto simples e HTML do lembrete."""
    top = ", ".join(f"{h['symbol']} {'+' if h['pct'] >= 0 else '−'}{br(abs(h['pct']))}%" for h in hits[:3])
    extra = f" e mais {len(hits) - 3}" if len(hits) > 3 else ""
    subject = f"[Ações B3] {len(hits)} com variação forte hoje · {top}{extra}"
    hora = now.strftime("%d/%m/%Y às %H:%M")

    lines = [f"Lembrete de variação das ações ({hora}, horário de Brasília)", ""]
    for h in hits:
        novo = "  [NOVO NÍVEL]" if h["symbol"] in new_symbols else ""
        lines.append(
            f"{h['symbol']:<6} R$ {br(h['price']):>8}  {'+' if h['pct'] >= 0 else '−'}{br(abs(h['pct']))}%  "
            f"(nível {h['level']}%){novo}"
        )
    lines += ["", "Níveis de alerta: ±2%, ±4% e ±8% em relação ao fechamento anterior.",
              "Dados do Yahoo Finance, com atraso de até 15 min.", "", f"Painel: {DASHBOARD_URL}"]
    text = "\n".join(lines)

    from email_layout import UP, DOWN, INK, MUTED, FONT, data_table, section_title, row, button, page, esc
    rows = []
    for h in hits:
        up = h["pct"] >= 0
        col = UP if up else DOWN
        novo = ' <span style="background:#fde68a;color:#111827;padding:1px 6px;font-size:11px;font-weight:700">NOVO</span>' if h["symbol"] in new_symbols else ""
        rows.append([f'<b>{esc(h["symbol"])}</b>{novo}<div style="font-size:12px;color:{MUTED}">{esc(h["name"])}</div>',
                     f'<b>R$ {br(h["price"])}</b>',
                     f'<b style="color:{col}">{"▲" if up else "▼"} {"+" if up else "−"}{br(abs(h["pct"]))}%</b>',
                     f'<b style="color:{col}">{"+" if up else "−"}{h["level"]}%</b>'])
    quiet = [q for q in quotes if q["symbol"] not in {h["symbol"] for h in hits} and day_change(q) is not None]
    quiet_txt = " · ".join(f'<b>{esc(q["symbol"])}</b> <span style="color:{UP if day_change(q) >= 0 else DOWN}">'
                           f'{"+" if day_change(q) >= 0 else "−"}{br(abs(day_change(q)))}%</span>' for q in quiet)
    html = page("LEMBRETE DE VARIAÇÃO · B3",
                f"{len(hits)} {'ação passou' if len(hits) == 1 else 'ações passaram'} dos níveis de alerta hoje",
                f"{hora} (Brasília) · variação contra o fechamento anterior",
                data_table(["Ação", "Preço", "Dia", "Nível"], rows, ["left", "right", "right", "center"])
                + (section_title("Demais ações") + row(quiet_txt) if quiet_txt else "")
                + button(DASHBOARD_URL, "Abrir painel com os gráficos"),
                "Níveis de alerta: ±2%, ±4% e ±8%. <b>NOVO</b> marca a ação que subiu de nível desde o último lembrete. "
                "Enviado a cada 2 horas durante o pregão enquanto houver ação acima de ±2%. Dados do Yahoo Finance, com atraso de até 15 min.")
    return subject, text, html


def send_email(subject, text, html):
    smtp_user = os.environ["SMTP_USER"]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = os.environ.get("EMAIL_FROM") or smtp_user
    msg["To"] = os.environ["EMAIL_TO"]
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT") or 587)) as server:
        server.starttls()
        server.login(smtp_user, os.environ["SMTP_PASS"])
        server.sendmail(msg["From"], [a.strip() for a in msg["To"].split(",")], msg.as_string())


# ---------------------------------------------------------------- principal
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="não envia; salva alerts/preview.html")
    ap.add_argument("--demo", action="store_true", help="usa dados simulados")
    ap.add_argument("--no-email", action="store_true", help="só atualiza alerts/prices.json (para o painel)")
    args = ap.parse_args()

    now = datetime.now(BRT)
    OUT_DIR.mkdir(exist_ok=True)

    quotes, errors = [], []
    session = requests.Session()
    session.headers.update(HEADERS)
    for t in TICKERS:
        try:
            quotes.append(demo_quote(t) if args.demo else fetch_quote(session, t))
        except Exception as e:
            errors.append(str(e))
            print(f"[ERRO] {e}")
    if not quotes:
        print("[ERRO] Nenhuma cotação obtida.")
        sys.exit(1)

    if not args.demo:
        try:
            funds = load_fundamentals(session, [q["symbol"] for q in quotes])
            prices = {q["symbol"]: q.get("price") for q in quotes}
            for q in quotes:
                attach_fundamentals(q, funds.get(q["symbol"]), prices)
        except Exception as e:
            print(f"[AVISO] fundamentos: {e}")

    # foto para o dashboard
    PRICES_FILE.write_text(json.dumps({
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Yahoo Finance",
        "quotes": quotes,
    }, ensure_ascii=False))

    if args.no_email:
        print(f"[INFO] Foto de preços atualizada ({len(quotes)} ações); sem e-mail nesta execução.")
        return

    # feriado / dia sem pregão: a última cotação não é de hoje
    today = now.date()
    traded_today = [q for q in quotes if q.get("marketTime")
                    and datetime.fromtimestamp(q["marketTime"], BRT).date() == today]
    if not traded_today:
        print("[INFO] Sem pregão hoje; nenhum e-mail enviado.")
        return

    hits = []
    for q in traded_today:
        pct = day_change(q)
        if pct is not None and level_of(pct):
            hits.append({"symbol": q["symbol"], "name": q["name"], "price": q["price"],
                         "pct": pct, "level": level_of(pct)})
    hits.sort(key=lambda h: abs(h["pct"]), reverse=True)

    # nível já avisado hoje, para marcar o que é NOVO
    state = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            state = {}
    if state.get("date") != today.isoformat():
        state = {"date": today.isoformat(), "levels": {}}
    new_symbols = {h["symbol"] for h in hits if h["level"] > state["levels"].get(h["symbol"], 0)}
    for h in hits:
        state["levels"][h["symbol"]] = max(h["level"], state["levels"].get(h["symbol"], 0))

    if not hits:
        print("[INFO] Nenhuma ação passou de ±2% hoje; nenhum e-mail enviado.")
        STATE_FILE.write_text(json.dumps(state, indent=2))
        return

    subject, text, html = build_email(hits, traded_today, now, new_symbols)
    print(subject)
    print(text)
    if args.dry_run:
        (OUT_DIR / "preview.html").write_text(html)
        print(f"[INFO] Prévia salva em {OUT_DIR / 'preview.html'} (nada enviado).")
        return

    send_email(subject, text, html)
    STATE_FILE.write_text(json.dumps(state, indent=2))
    print("[INFO] E-mail enviado.")


if __name__ == "__main__":
    main()
