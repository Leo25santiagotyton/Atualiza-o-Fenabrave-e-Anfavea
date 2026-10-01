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
from datetime import date, datetime
from pathlib import Path

from alerta_acoes import DASHBOARD_URL, br, send_email
from debentures_anbima import FAVORITES

DEB_FILE = Path(__file__).parent / "alerts" / "debentures.json"
BONDS_FILE = Path(__file__).parent / "alerts" / "bonds.json"
BOND_FOCUS = ["OHI Group"]          # bonds em destaque no topo da seção
CRA_FOCUS = "Vamos"                 # grupo cujos CRAs entram com negócio a negócio da B3
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


def _interp(pts, x):
    if not pts:
        return None
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def usd_to_cdi(ytm, dur, curve):
    """CDI + de um bond (YTM semestral) na duration, pelo cupom cambial limpo da B3 (FRC) — mesma conta da aba Swap Dólar +."""
    doc = ((curve or {}).get("usd") or {}).get("DOC") or []
    if ytm is None or not dur or not doc:
        return None
    dc = dur * 365
    du = _interp([(v[0], v[1]) for v in doc], dc) or dc * 252 / 365
    cc = _interp([(v[0], v[2]) for v in doc], dc)
    y = ((1 + ytm / 200) ** 2 - 1)
    return (((1 + y) ** (dc / 360) / (1 + cc / 100 * dc / 360)) ** (252 / du) - 1) * 100


def bond_section(curve):
    """Bonds em US$ do monitor Bloomberg (alerts/bonds.json), com os de BOND_FOCUS no topo."""
    from email_layout import DOWN, MUTED, UP, data_table, esc, row, section_title
    if not BONDS_FILE.exists():
        return "", ""
    bd = json.loads(BONDS_FILE.read_text())
    bonds = sorted(bd.get("bonds", []), key=lambda b: (b["issuer"] not in BOND_FOCUS, b["issuer"]))
    bps = lambda v: "—" if v is None else f'<b style="color:{DOWN if v > 0 else UP if v < 0 else MUTED}">{"+" if v > 0 else "−" if v < 0 else ""}{round(abs(v))}</b>'
    rows, txt = [], []
    for b in bonds:
        cdi = usd_to_cdi(b.get("ytm"), b.get("dur"), curve)
        star = b["issuer"] in BOND_FOCUS
        name = f"{'★ ' if star else ''}<b>{esc(b['issuer'])}</b><div style='font-size:12px;color:{MUTED}'>{esc(b.get('bond') or '')} · {esc(b.get('rating') or '—')}</div>"
        rows.append([name, br(b.get("px")) if b.get("px") is not None else "—", f"<b>{br(b.get('ytm'))}%</b>" if b.get("ytm") is not None else "—",
                     bps(b.get("d1")), bps(b.get("d1w")), f"{round(b['zspr'])}" if b.get("zspr") is not None else "—",
                     f"<b>{br(cdi)}%</b>" if cdi is not None else "—"])
        txt.append(f"  {'★ ' if star else ''}{b['issuer']} {b.get('bond')}: preço {br(b.get('px'))}, YTM {br(b.get('ytm'))}% "
                   f"({'+' if (b.get('d1') or 0) > 0 else ''}{round(b.get('d1') or 0)} bps no dia), CDI + {br(cdi) if cdi is not None else '—'}%")
    html_out = (section_title(f"Bonds em US$ · monitor Bloomberg ({bd.get('updatedLabel') or ''})")
                + data_table(["Bond", "Preço", "YTM", "Δ 1D (bps)", "Δ 1S (bps)", "Z-spread", "CDI +"], rows)
                + row(f'<span style="color:{MUTED};font-size:12px">CDI + pelo cupom cambial limpo da B3 (FRC) na duration do bond. ★ = destaque.</span>'))
    return html_out, "Bonds em US$:\n" + "\n".join(txt)


def cra_section(papers, day=None):
    """CRAs do grupo CRA_FOCUS com os negócios do último pregão na B3 (Boletim Diário, negócio a negócio)."""
    from email_layout import DOWN, MUTED, UP, data_table, esc, row, section_title
    cras = [p for p in papers if p.get("section") in ("CRA", "CRI") and p.get("issuer") == CRA_FOCUS]
    if not cras:
        return "", ""
    days = sorted({t[0] for p in cras for t in p.get("ticks", [])})
    d = day if day in days else (days[-1] if days else None)
    rows, txt = [], []
    for p in sorted(cras, key=lambda p: p["code"]):
        ticks = p.get("ticks", [])
        dts = sorted({t[0] for t in ticks})
        today_t = [t for t in ticks if t[0] == d]
        prev_d = max((x for x in dts if d and x < d), default=None)
        vw = lambda ts: (sum(t[5] * t[4] for t in ts if t[5] is not None and t[4]) / sum(t[4] for t in ts if t[5] is not None and t[4])) if any(t[5] is not None and t[4] for t in ts) else None
        r_now, r_prev = vw(today_t), vw([t for t in ticks if t[0] == prev_d])
        vol = sum(t[4] or 0 for t in today_t)
        delta = (r_now - r_prev) * 100 if r_now is not None and r_prev is not None else None
        last = max(today_t, key=lambda t: t[1]) if today_t else (max(ticks, key=lambda t: t[0] + t[1]) if ticks else None)
        emi = (p.get("details") or {}).get("Remuneração na emissão") or p.get("index") or ""
        big = vol >= 1_000_000
        rows.append([f"<b>{esc(p['code'])}</b><div style='font-size:12px;color:{MUTED}'>{esc(emi)} · venc. {esc(p.get('maturity') or '—')}</div>",
                     str(len(today_t)) if today_t else "—",
                     (f"<b><u>R$ {br(vol / 1e6)} mi</u></b>" if big else f"R$ {br(vol / 1e6)} mi") if vol else "—",
                     f"<b>{br(r_now)}%</b>" if r_now is not None else "—",
                     f'<b style="color:{DOWN if delta > 0 else UP}">{"+" if delta > 0 else "−"}{round(abs(delta))} bps</b>' if delta else "—",
                     f"{datetime.fromisoformat(last[0]).strftime('%d/%m')} {last[1][:5]} · {br(last[5])}%" if last and last[5] is not None else "—"])
        if today_t:
            txt.append(f"  {p['code']}: {len(today_t)} negócios, R$ {br(vol / 1e6)} mi, taxa média {br(r_now)}%"
                       + (f" ({'+' if delta > 0 else ''}{round(delta)} bps)" if delta else ""))
    dd = datetime.fromisoformat(d).strftime("%d/%m/%Y") if d else "—"
    html_out = (section_title(f"CRAs da {CRA_FOCUS} · negócios na B3 em {dd}")
                + data_table(["CRA", "Negócios", "Volume", "Taxa média", "vs dia anterior", "Último negócio"], rows)
                + row(f'<span style="color:{MUTED};font-size:12px">Boletim Diário da B3 (renda fixa, negócio a negócio). Taxa média ponderada pelo volume. Volume acima de R$ 1 milhão sublinhado.</span>'))
    return html_out, f"CRAs da {CRA_FOCUS} em {dd}:\n" + ("\n".join(txt) or "  sem negócios")


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
    if BONDS_FILE.exists():  # bonds em destaque no assunto (ex.: OHI)
        for b in json.loads(BONDS_FILE.read_text()).get("bonds", []):
            if b["issuer"] in BOND_FOCUS and b.get("ytm") is not None:
                d1 = b.get("d1")
                subject += f" · {b['issuer'].split()[0]} {br(b['ytm'])}%" + (f" ({'+' if d1 > 0 else ''}{round(d1)} bps)" if d1 else "")

    bonds_html, bonds_txt = bond_section(data.get("curveLatest"))
    cra_html, cra_txt = cra_section(papers)
    from email_layout import MUTED, row, button, page, esc
    miss_html = row(f'<span style="color:{MUTED}">Favoritos sem taxa ANBIMA no dia: {esc(", ".join(missing))}.</span>') if missing else ""
    html_body = page("CRÉDITO · DEBÊNTURES NO SECUNDÁRIO", f"Fechamento ANBIMA de {dd}",
                     "Variação da taxa indicativa contra o dia útil anterior",
                     fav_html + miss_html + cra_html + bonds_html + all_html + button(DASHBOARD_URL, "Abrir o painel"),
                     "Fonte: taxas indicativas ANBIMA e negócios do SND. Fechar = taxa cai (papel valoriza); abrir = taxa sobe. "
                     "NTN-B + = (1 + taxa) / (1 + NTN-B de referência) − 1. CDI + usa a inflação implícita e a curva prefixada "
                     "da ETTJ ANBIMA (aproximação da curva DI).")
    text = "\n\n".join(x for x in [f"Fechamento ANBIMA {dd}", fav_txt, cra_txt, bonds_txt, all_txt, f"Painel: {DASHBOARD_URL}"] if x)
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
