"""
Alerta de negócios relevantes nos favoritos (SND)
-------------------------------------------------
Roda a cada 2 horas nos dias úteis. Consulta os negócios do dia (e do dia útil
anterior, que o SND às vezes publica com atraso) e envia e-mail quando um papel
favorito negociou mais de R$ 1 milhão no dia e ainda não foi avisado.

A taxa média é aproximada a partir do PU médio negociado, usando a taxa, o PU e
a duration mais recentes da ANBIMA (alerts/debentures.json).

Uso:
  python alerta_trades.py            # envia se houver
  python alerta_trades.py --dry-run  # não envia; salva alerts/trades_preview.html
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import requests

from alerta_acoes import BRT, DASHBOARD_URL, HEADERS, br, send_email
from debentures_anbima import FAVORITES
from email_layout import DOWN, MUTED, UP, button, data_table, esc, page, row
from negocios_snd import fetch_trades

OUT = Path(__file__).parent / "alerts"
DEB_FILE = OUT / "debentures.json"
STATE_FILE = OUT / "trades_state.json"
MIN_VOLUME = 1_000_000


def prev_business_day(d):
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def implied(paper, t):
    """Taxa média aproximada do negócio pela última taxa/PU/duration ANBIMA do papel."""
    s = [x for x in (paper or {}).get("series", []) if x[1] is not None and x[2] and x[3]]
    if not s or not t["puAvg"]:
        return None, None
    last = s[-1]
    mod = (last[3] / 252) / (1 + last[1] / 100)
    if not mod:
        return None, None
    rate = last[1] + (last[2] / t["puAvg"] - 1) / mod * 100
    return rate, (rate - last[1]) * 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)

    deb = json.loads(DEB_FILE.read_text()) if DEB_FILE.exists() else {}
    papers = {p["code"]: p for p in deb.get("papers", [])}
    favs = deb.get("favoritesDefault") or FAVORITES

    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {"sent": {}}
    cutoff = (datetime.now(BRT).date() - timedelta(days=10)).isoformat()
    state["sent"] = {k: v for k, v in state.get("sent", {}).items() if v >= cutoff}

    s = requests.Session()
    s.headers.update(HEADERS)
    today = datetime.now(BRT).date()
    hits = []
    for d in (prev_business_day(today), today):
        try:
            trades = fetch_trades(s, d)
        except Exception as e:
            print(f"[ERRO] SND {d}: {e}")
            continue
        for t in trades:
            if t["code"] not in favs or t["qty"] is None or t["puAvg"] is None:
                continue
            vol = t["qty"] * t["puAvg"]
            if vol < MIN_VOLUME:
                continue
            key = f"{t['code']}|{t['date']}|{int(t['qty'])}"
            if key in state["sent"]:
                continue
            p = papers.get(t["code"], {})
            rate, bps = implied(p, t)
            hits.append({"t": t, "vol": vol, "key": key, "paper": p, "rate": rate, "bps": bps})
        print(f"[INFO] SND {d}: {len(trades)} linhas lidas.")

    if not hits:
        print("[INFO] Nenhum negócio novo acima de R$ 1 milhão nos favoritos.")
        STATE_FILE.write_text(json.dumps(state, indent=1))
        return

    hits.sort(key=lambda h: -h["vol"])
    rows = []
    for h in hits:
        t, p = h["t"], h["paper"]
        idx = (p.get("index") or "").split("+")[0].strip() or ""
        rate_txt = f"{idx} + {br(h['rate'])}%" if h["rate"] is not None and idx else (f"{br(h['rate'])}%" if h["rate"] is not None else "—")
        bps_txt = (f'<b style="color:{DOWN if h["bps"] > 0 else UP}">{"+" if h["bps"] > 0 else "−"}{round(abs(h["bps"]))} bps</b>'
                   if h["bps"] is not None else "—")
        rows.append([f"<b><u>{esc(t['code'])}</u></b><div style='font-size:12px;color:{MUTED}'>{esc(p.get('issuer') or t['issuer'])}</div>",
                     esc(datetime.fromisoformat(t["date"]).strftime("%d/%m")),
                     f"<b><u>R$ {br(h['vol'] / 1e6)} mi</u></b>", f"{int(t['qty'])} · {int(t['deals'] or 0)} neg.",
                     f"{br(t['puAvg'])}", f"<b>{rate_txt}</b>", bps_txt])
    html_body = page("CRÉDITO · NEGÓCIO RELEVANTE NOS FAVORITOS",
                     f"{len(hits)} negócio(s) acima de R$ 1 milhão",
                     f"Consulta das {datetime.now(BRT).strftime('%H:%M')} no SND (debentures.com.br)",
                     data_table(["Papel", "Dia", "Volume", "Qtd · negócios", "PU médio", "Taxa média (aprox.)", "vs ANBIMA"], rows)
                     + row(f'<span style="color:{MUTED};font-size:12px">Taxa média aproximada pelo PU médio negociado e pela última taxa, PU e duration da ANBIMA. '
                           f'Positivo = negociou com taxa acima da ANBIMA (preço abaixo).</span>')
                     + button(DASHBOARD_URL, "Abrir aba Dívida"),
                     "Favoritos acompanhados: " + ", ".join(favs) + ". Aviso enviado uma vez por papel e dia (novo aviso se o volume do dia mudar).")
    text = "\n".join(f"{h['t']['code']} {h['t']['date']}: R$ {br(h['vol'] / 1e6)} mi, PU médio {br(h['t']['puAvg'])}"
                     + (f", taxa ~{br(h['rate'])}% ({round(h['bps'])} bps vs ANBIMA)" if h["rate"] is not None else "") for h in hits)
    subject = "[Crédito] Negócio relevante: " + ", ".join(f"{h['t']['code']} R$ {br(h['vol'] / 1e6, 1)} mi" for h in hits[:3])
    print(subject)
    print(text)
    if args.dry_run:
        (OUT / "trades_preview.html").write_text(html_body)
        return
    send_email(subject, text + f"\n\nPainel: {DASHBOARD_URL}", html_body)
    for h in hits:
        state["sent"][h["key"]] = h["t"]["date"]
    STATE_FILE.write_text(json.dumps(state, indent=1))
    print("[INFO] E-mail enviado.")


if __name__ == "__main__":
    main()
