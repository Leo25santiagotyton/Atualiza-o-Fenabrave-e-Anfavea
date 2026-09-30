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
    from email_layout import MUTED, FONT, data_table, row, esc
    head = row(f'<b style="font:700 14px {FONT};color:{color}">{esc(title)}</b>', "10px 16px 4px")
    if not rows:
        return head + row(f'<span style="color:{MUTED}">Sem papéis com variação.</span>')
    body = [[f'<b>{esc(m["p"]["code"])}</b><div style="font-size:12px;color:{MUTED}">{esc(m["p"].get("issuer") or "")} · {esc(m["p"].get("index") or "")}</div>',
             f'<b>{rate_txt(m["p"], m["rate"])}</b>',
             f'<b style="color:{color}">{delta_txt(m)}</b>',
             (f'NTN-B + <b>{br(m["ntnb"])}%</b>' if m["ntnb"] is not None else "—")
             + (f'<div style="font-size:12px;color:{MUTED}">CDI + {br(m["cdi"])}%</div>' if m["cdi"] is not None else ""),
             f'R$ {br(m["vol"] / 1e6)} mi' if m["vol"] else "—"] for m in rows]
    return head + data_table(["Papel", "Taxa ANBIMA", "No dia", "Swap", "Volume SND"], body)


def section(label, ms):
    from email_layout import UP, DOWN, section_title
    closed = sorted([m for m in ms if m["bps"] < 0], key=lambda m: m["bps"])[:TOP]
    opened = sorted([m for m in ms if m["bps"] > 0], key=lambda m: -m["bps"])[:TOP]
    body = (section_title(f"{label} · {len(ms)} papéis com taxa")
            + table(f"Top {TOP} que mais fecharam (taxa caiu, papel valorizou)", closed, UP)
            + table(f"Top {TOP} que mais abriram (taxa subiu, papel desvalorizou)", opened, DOWN))
    lines = [f"{label}:"]
    lines += [f"  fechou {m['p']['code']}: {rate_txt(m['p'], m['rate'])} ({delta_txt(m)})" for m in closed]
    lines += [f"  abriu  {m['p']['code']}: {rate_txt(m['p'], m['rate'])} ({delta_txt(m)})" for m in opened]
    return body, "\n".join(lines), closed, opened


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

    from email_layout import MUTED, row, button, page, esc
    miss_html = row(f'<span style="color:{MUTED}">Favoritos sem taxa ANBIMA no dia: {esc(", ".join(missing))}.</span>') if missing else ""
    html_body = page("CRÉDITO · DEBÊNTURES NO SECUNDÁRIO", f"Fechamento ANBIMA de {dd}",
                     "Variação da taxa indicativa contra o dia útil anterior",
                     fav_html + miss_html + all_html + button(DASHBOARD_URL, "Abrir aba Dívida no painel"),
                     "Fonte: taxas indicativas ANBIMA e negócios do SND. Fechar = taxa cai (papel valoriza); abrir = taxa sobe. "
                     "NTN-B + = (1 + taxa) / (1 + NTN-B de referência) − 1. CDI + usa a inflação implícita e a curva prefixada "
                     "da ETTJ ANBIMA (aproximação da curva DI).")
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
