"""
Layout comum dos e-mails, pensado para Outlook (inclusive modo escuro) e Gmail:
tudo em tabelas com bgcolor explícito, fundo claro, texto escuro de alto contraste
e cores fortes para alta/queda. Sem div com fundo, sem border-radius obrigatório.
"""

import html as _html

INK = "#111827"      # texto principal
MUTED = "#4b5563"    # texto secundário (contraste AA sobre branco)
LINE = "#d1d5db"
HEAD_BG = "#0b2545"  # faixa do título
HEAD_FG = "#ffffff"
ACCENT = "#b45309"   # rótulo do boletim
UP = "#0a7d32"
DOWN = "#b91c1c"
PANEL = "#f3f4f6"
LINK = "#1d4ed8"
FONT = "Segoe UI, Roboto, Arial, sans-serif"


def esc(s):
    return _html.escape(str(s if s is not None else ""))


def color_for(v, invert=False):
    if v is None or v == 0:
        return INK
    up = v > 0
    if invert:
        up = not up
    return UP if up else DOWN


def section_title(text):
    return (f'<tr><td bgcolor="{PANEL}" style="background:{PANEL};padding:8px 16px;font:700 12px {FONT};'
            f'color:{INK};letter-spacing:.04em;text-transform:uppercase;border-top:1px solid {LINE};border-bottom:1px solid {LINE}">'
            f'{esc(text)}</td></tr>')


def row(inner, pad="10px 16px"):
    return (f'<tr><td bgcolor="#ffffff" style="background:#ffffff;padding:{pad};font:14px {FONT};color:{INK};'
            f'border-bottom:1px solid {LINE}">{inner}</td></tr>')


def data_table(headers, rows, align=None):
    """Tabela de dados: headers = [str], rows = [[html]], align = ['left'|'right'...]."""
    align = align or ["left"] + ["right"] * (len(headers) - 1)
    th = "".join(f'<th align="{a}" style="padding:6px 10px;font:700 11px {FONT};color:{MUTED};border-bottom:1px solid {LINE};'
                 f'text-align:{a};white-space:nowrap">{esc(h)}</th>' for h, a in zip(headers, align))
    trs = "".join("<tr>" + "".join(
        f'<td align="{a}" style="padding:8px 10px;font:13px {FONT};color:{INK};border-bottom:1px solid {LINE};'
        f'text-align:{a};vertical-align:top">{c}</td>' for c, a in zip(r, align)) + "</tr>" for r in rows)
    return (f'<tr><td bgcolor="#ffffff" style="background:#ffffff;padding:0 6px">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="border-collapse:collapse;width:100%"><tr>{th}</tr>{trs}</table></td></tr>')


def button(url, label):
    return (f'<tr><td bgcolor="#ffffff" style="background:#ffffff;padding:16px">'
            f'<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td bgcolor="{LINK}" style="background:{LINK};padding:10px 18px">'
            f'<a href="{esc(url)}" style="font:700 14px {FONT};color:#ffffff;text-decoration:none">{esc(label)}</a>'
            f'</td></tr></table></td></tr>')


def page(eyebrow, title, subtitle, body_rows, footer):
    """Documento completo. body_rows = string com <tr>…</tr> da tabela principal."""
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light only">
<title>{esc(title)}</title></head>
<body style="margin:0;padding:0;background:#e5e7eb" bgcolor="#e5e7eb">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#e5e7eb" style="background:#e5e7eb">
<tr><td align="center" style="padding:20px 10px">
  <table role="presentation" width="680" cellpadding="0" cellspacing="0" border="0" bgcolor="#ffffff"
         style="width:680px;max-width:100%;background:#ffffff;border:1px solid {LINE};border-collapse:collapse">
    <tr><td bgcolor="{HEAD_BG}" style="background:{HEAD_BG};padding:16px 18px">
      <div style="font:700 12px {FONT};color:#fbbf24;letter-spacing:.08em">{esc(eyebrow)}</div>
      <div style="font:600 22px {FONT};color:{HEAD_FG};margin-top:4px">{esc(title)}</div>
      {f'<div style="font:13px {FONT};color:#dbeafe;margin-top:4px">{esc(subtitle)}</div>' if subtitle else ''}
    </td></tr>
    {body_rows}
  </table>
  <table role="presentation" width="680" cellpadding="0" cellspacing="0" border="0" style="width:680px;max-width:100%">
    <tr><td style="padding:12px 6px;font:12px {FONT};color:{MUTED};line-height:1.5">{footer}</td></tr>
  </table>
</td></tr></table>
</body></html>"""
