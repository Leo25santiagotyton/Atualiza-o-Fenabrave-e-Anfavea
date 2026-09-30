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
"""

import argparse
import json
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
    "RAPT4", "RENT3", "FRAS3", "ARML3", "MILS3", "PRNR3",
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

    month = []
    try:
        m = fetch_chart(session, ticker, "1mo", "1d")
        mq = (m.get("indicators", {}).get("quote") or [{}])[0]
        month = [[t, round(c, 4)] for t, c in zip(m.get("timestamp") or [], mq.get("close") or []) if c is not None]
    except Exception as e:
        print(f"[AVISO] {e}")

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
        "month": month,
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
        "month": [[now - (22 - i) * 86400, round(prev * (1 + rnd.gauss(0, 0.03)), 2)] for i in range(22)],
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

    def row(h):
        up = h["pct"] >= 0
        color, bg = ("#137333", "#e6f4ea") if up else ("#c5221f", "#fce8e6")
        seta = "▲" if up else "▼"
        novo = ('<span style="margin-left:6px;padding:1px 6px;border-radius:6px;background:#fdf1d8;'
                'color:#8a5a00;font-size:11px;font-weight:700">NOVO</span>') if h["symbol"] in new_symbols else ""
        return f"""
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid #e2e6eb;font-weight:700">{h['symbol']}{novo}
            <div style="font-weight:400;color:#5d6570;font-size:12px">{h['name']}</div></td>
          <td style="padding:10px 12px;border-bottom:1px solid #e2e6eb;text-align:right">R$ {br(h['price'])}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e2e6eb;text-align:right;color:{color};font-weight:700">
            {seta} {'+' if up else '−'}{br(abs(h['pct']))}%</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e2e6eb;text-align:center">
            <span style="display:inline-block;padding:2px 8px;border-radius:6px;background:{bg};color:{color};
              font-weight:700;font-size:12px">{'+' if up else '−'}{h['level']}%</span></td>
        </tr>"""

    quiet = [q for q in quotes if q["symbol"] not in {h["symbol"] for h in hits} and day_change(q) is not None]
    quiet_txt = " · ".join(
        f"{q['symbol']} {'+' if day_change(q) >= 0 else '−'}{br(abs(day_change(q)))}%" for q in quiet
    )

    html = f"""<!doctype html><html><body style="margin:0;background:#f5f7fa;font-family:Roboto,Arial,sans-serif;color:#1f2328">
  <div style="max-width:620px;margin:0 auto;padding:24px 16px">
    <div style="background:#ffffff;border:1px solid #e2e6eb;border-radius:12px;overflow:hidden">
      <div style="padding:18px 20px;border-bottom:1px solid #e2e6eb">
        <div style="font-size:12px;color:#5d6570;text-transform:uppercase;letter-spacing:.06em">Lembrete de variação · B3</div>
        <div style="font-size:20px;margin-top:4px">{len(hits)} {'ação passou' if len(hits) == 1 else 'ações passaram'} dos níveis de alerta hoje</div>
        <div style="font-size:13px;color:#5d6570;margin-top:4px">{hora} (Brasília) · variação contra o fechamento anterior</div>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:14px">
        <tr style="background:#f5f7fa;color:#5d6570;font-size:12px">
          <th style="padding:8px 12px;text-align:left;font-weight:500">Ação</th>
          <th style="padding:8px 12px;text-align:right;font-weight:500">Preço</th>
          <th style="padding:8px 12px;text-align:right;font-weight:500">Dia</th>
          <th style="padding:8px 12px;text-align:center;font-weight:500">Nível</th>
        </tr>{''.join(row(h) for h in hits)}
      </table>
      {f'<div style="padding:14px 20px;font-size:12px;color:#5d6570"><b style="color:#1f2328">Demais ações:</b> {quiet_txt}</div>' if quiet_txt else ''}
      <div style="padding:0 20px 18px"><a href="{DASHBOARD_URL}" style="display:inline-block;padding:8px 16px;border-radius:8px;
        background:#1a5fd1;color:#ffffff;text-decoration:none;font-size:13px;font-weight:500">Abrir painel com os gráficos</a></div>
    </div>
    <p style="font-size:11px;color:#5d6570;line-height:1.5;margin:14px 4px 0">
      Níveis de alerta: ±2%, ±4% e ±8%. <b>NOVO</b> marca a ação que subiu de nível desde o último lembrete.
      Enviado a cada 2 horas durante o pregão enquanto houver ação acima de ±2%. Dados do Yahoo Finance, com atraso de até 15 min.
    </p>
  </div>
</body></html>"""
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

    # foto para o dashboard
    PRICES_FILE.write_text(json.dumps({
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Yahoo Finance",
        "quotes": quotes,
    }, ensure_ascii=False))

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
