"""
Boletim diário de crédito (debêntures ANBIMA)
---------------------------------------------
Todo dia útil às 8h50: a partir de alerts/debentures.json, mostra quais papéis
mais fecharam (taxa caiu) e mais abriram (taxa subiu) no último dia da ANBIMA,
primeiro entre os favoritos e depois no geral dos emissores acompanhados.
Inclui NTN-B +/CDI + dos papéis IPCA+ e o volume negociado no SND.

E-mail via as mesmas variáveis do monitor:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM, EMAIL_TO

Uso:
  python boletim_credito.py            # envia
  python boletim_credito.py --dry-run  # salva alerts/credito_preview.html
"""

import argparse
import html
import json
import sys
from datetime import date
from pathlib import Path

from alerta_acoes import DASHBOARD_URL, br, send_email
from debentures_anbima import FAVORITES

DEB_FILE = Path(__file__).parent / "alerts" / "debentures.json"
TOP = 5


def pct_di(p):
    return "PERCENT" in (p.get("section") or "") or ("%" in (p.get("index") or "") and "+" not in (p.get("index") or ""))


def rate_txt(p, r):
    if r is None:
        return "—"
    if pct_di(p):
        return f"{br(r)}% do DI"
    idx = (p.get("index") or "").strip().upper()
    for k in ("IPCA", "DI", "IGP"):
        if idx.startswith(k):
            return f"{k} + {br(r)}%"
    return f"{br(r)}%"


def moves(papers, day):
    """Variação da taxa ANBIMA no dia `day` contra o dia anterior com taxa, por papel."""
    out = []
    for p in papers:
        s = [x for x in p.get("series", []) if x[1] is not None]
        if len(s) < 2 or s[-1][0] != day:
            continue
        cur, prev = s[-1], s[-2]
        delta = cur[1] - prev[1]
        vol = sum((t[1] or 0) * (t[4] or 0) for t in p.get("trades", []) if t[0] == day)
        out.append({"p": p, "rate": cur[1], "bps": delta * 100 if not pct_di(p) else delta, "pp": pct_di(p),
                    "ntnb": cur[6] if len(cur) > 6 else None, "cdi": cur[7] if len(cur) > 7 else None,
                    "pu": cur[2], "vol": vol, "prevDay": prev[0]})
    return out


def delta_txt(m):
    v = m["bps"]
    s = "+" if v > 0 else "−" if v < 0 else ""
    return f"{s}{br(abs(v))} p.p." if m["pp"] else f"{s}{round(abs(v))} bps"


def table(title, rows, color):
    if not rows:
        return f'<div style="padding:10px 16px;color:#5d6570;font-size:13px">{html.escape(title)}: sem papéis com variação.</div>'
    trs = "".join(f"""
      <tr>
        <td style="padding:7px 10px;border-bottom:1px solid #e2e6eb"><b>{html.escape(m['p']['code'])}</b>
          <div style="font-size:11px;color:#5d6570">{html.escape(m['p'].get('issuer') or '')} · {html.escape(m['p'].get('index') or '')}</div></td>
        <td style="padding:7px 10px;border-bottom:1px solid #e2e6eb;text-align:right">{rate_txt(m['p'], m['rate'])}</td>
        <td style="padding:7px 10px;border-bottom:1px solid #e2e6eb;text-align:right;color:{color};font-weight:700">{delta_txt(m)}</td>
        <td style="padding:7px 10px;border-bottom:1px solid #e2e6eb;text-align:right;font-size:12px">{'NTN-B + ' + br(m['ntnb']) + '%' if m['ntnb'] is not None else '—'}
          <div style="color:#5d6570">{'CDI + ' + br(m['cdi']) + '%' if m['cdi'] is not None else ''}</div></td>
        <td style="padding:7px 10px;border-bottom:1px solid #e2e6eb;text-align:right;font-size:12px">{'R$ ' + br(m['vol'] / 1e6) + ' mi' if m['vol'] else '—'}</td>
      </tr>""" for m in rows)
    return f"""
    <div style="padding:10px 16px 2px;font-size:13px;font-weight:700;color:{color}">{html.escape(title)}</div>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <tr style="color:#5d6570;font-size:11px"><th style="text-align:left;padding:4px 10px;font-weight:500">Papel</th>
        <th style="text-align:right;padding:4px 10px;font-weight:500">Taxa ANBIMA</th><th style="text-align:right;padding:4px 10px;font-weight:500">No dia</th>
        <th style="text-align:right;padding:4px 10px;font-weight:500">Swap</th><th style="text-align:right;padding:4px 10px;font-weight:500">Volume SND</th></tr>
      {trs}
    </table>"""


def section(label, ms):
    closed = sorted([m for m in ms if m["bps"] < 0], key=lambda m: m["bps"])[:TOP]
    opened = sorted([m for m in ms if m["bps"] > 0], key=lambda m: -m["bps"])[:TOP]
    body = table(f"Top {TOP} que mais fecharam (taxa caiu)", closed, "#137333") + table(f"Top {TOP} que mais abriram (taxa subiu)", opened, "#c5221f")
    head = f"""<div style="padding:14px 16px 4px;border-top:1px solid #e2e6eb;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#5d6570">{html.escape(label)} · {len(ms)} papéis com taxa</div>"""
    lines = [f"{label}:"]
    lines += [f"  fechou {m['p']['code']}: {rate_txt(m['p'], m['rate'])} ({delta_txt(m)})" for m in closed]
    lines += [f"  abriu  {m['p']['code']}: {rate_txt(m['p'], m['rate'])} ({delta_txt(m)})" for m in opened]
    return head + body, "\n".join(lines), closed, opened


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not DEB_FILE.exists():
        print("[ERRO] alerts/debentures.json não existe.")
        sys.exit(1)
    data = json.loads(DEB_FILE.read_text())
    day = data.get("lastDate")
    papers = data.get("papers", [])
    fav_codes = data.get("favoritesDefault") or FAVORITES
    all_moves = moves(papers, day)
    fav_moves = [m for m in all_moves if m["p"]["code"] in fav_codes]
    missing = [c for c in fav_codes if c not in {m["p"]["code"] for m in fav_moves}]

    fav_html, fav_txt, fc, fo = section("Favoritos", fav_moves)
    all_html, all_txt, ac, ao = section("Geral · todos os emissores", all_moves)
    dd = date.fromisoformat(day).strftime("%d/%m/%Y") if day else "—"
    top_line = ", ".join(f"{m['p']['code']} {delta_txt(m)}" for m in (ac[:2] + ao[:2]))
    subject = f"[Crédito] Fechamento ANBIMA {dd} · {top_line}" if top_line else f"[Crédito] Fechamento ANBIMA {dd}"

    miss_html = (f'<div style="padding:6px 16px;color:#5d6570;font-size:12px">Sem taxa ANBIMA no dia: {html.escape(", ".join(missing))}.</div>'
                 if missing else "")
    html_body = f"""<!doctype html><html><body style="margin:0;background:#f5f7fa;font-family:Roboto,Arial,sans-serif;color:#1f2328">
  <div style="max-width:720px;margin:0 auto;padding:20px 12px">
    <div style="background:#0f1216;border-radius:12px 12px 0 0;padding:16px 18px">
      <div style="color:#f5a623;font-size:12px;font-weight:700;letter-spacing:.08em">CRÉDITO · DEBÊNTURES NO SECUNDÁRIO</div>
      <div style="color:#ffffff;font-size:20px;margin-top:4px">Fechamento ANBIMA de {dd}</div>
      <div style="color:#8b939c;font-size:12px;margin-top:4px">Variação da taxa indicativa contra o dia útil anterior. Fechar = taxa cai (papel valoriza); abrir = taxa sobe.</div>
    </div>
    <div style="background:#ffffff;border:1px solid #e2e6eb;border-top:0;border-radius:0 0 12px 12px;overflow:hidden">
      {fav_html}{miss_html}{all_html}
      <div style="padding:14px 16px"><a href="{DASHBOARD_URL}" style="display:inline-block;padding:8px 16px;border-radius:8px;
        background:#1a5fd1;color:#ffffff;text-decoration:none;font-size:13px;font-weight:500">Abrir aba Dívida no painel</a></div>
    </div>
    <p style="font-size:11px;color:#5d6570;line-height:1.5;margin:12px 4px 0">
      Fonte: taxas indicativas ANBIMA e negócios do SND. NTN-B + = (1 + taxa) / (1 + NTN-B de referência) − 1.
      CDI + usa a inflação implícita e a curva prefixada da ETTJ ANBIMA (aproximação da curva DI).
    </p>
  </div>
</body></html>"""
    text = "\n\n".join([f"Fechamento ANBIMA {dd}", fav_txt, all_txt, f"Painel: {DASHBOARD_URL}"])
    print(subject)
    print(text)
    if args.dry_run:
        (DEB_FILE.parent / "credito_preview.html").write_text(html_body)
        print("[INFO] Prévia salva em alerts/credito_preview.html.")
        return
    send_email(subject, text, html_body)
    print("[INFO] E-mail enviado.")


if __name__ == "__main__":
    main()
