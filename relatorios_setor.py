"""
Relatórios mensais FENABRAVE e ANFAVEA em tabela
------------------------------------------------
Quando sai um relatório novo, baixa o PDF, extrai os números e manda um e-mail
com tabelas: volume do mês, mês anterior, mesmo mês do ano anterior, acumulado
do ano e as variações (mês/mês, ano/ano e acumulado).

- FENABRAVE: "Informativo - Emplacamentos" (página Conteudo/emplacamentos),
  resumo mensal por segmento (autos, comerciais leves, caminhões, ônibus,
  motos, implementos e outros).
- ANFAVEA: "Carta da Anfavea" (página conteudos/carta-da-anfavea), resumo de
  emplacamento, exportação e produção de autoveículos, e emplacamento por
  segmento.

Os relatórios já enviados ficam em alerts/setor_state.json, para não mandar o
mesmo duas vezes. E-mail via as mesmas variáveis do monitor:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM, EMAIL_TO

Uso:
  python relatorios_setor.py                  # envia o que for novo
  python relatorios_setor.py --dry-run        # não envia; salva alerts/setor_preview.html
  python relatorios_setor.py --force          # reenvia o último de cada fonte
"""

import argparse
import io
import json
import re
import sys
from pathlib import Path

import pdfplumber
import requests
from bs4 import BeautifulSoup

from alerta_acoes import send_email
from email_layout import DOWN, FONT, INK, MUTED, UP, button, data_table, esc, page, row, section_title
from monitor import BROWSER_HEADERS
import monitoramento

BASE = Path(__file__).parent / "alerts"
STATE_FILE = BASE / "setor_state.json"
PREVIEW_FILE = BASE / "setor_preview.html"

FENABRAVE_HOME = "https://www.fenabrave.org.br/portalv2/home/imprensa"
FENABRAVE_PAGE = "https://www.fenabrave.org.br/portalv2/Conteudo/emplacamentos"
ANFAVEA_PAGE = "https://anfavea.com.br/site/conteudos/carta-da-anfavea/"
ANFAVEA_HOME = "https://anfavea.com.br/site/"

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
MES_ABREV = {"JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6,
             "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12}


# ---------------------------------------------------------------- números
def num(s):
    """'1.728.390' -> 1728390 ; '1,57' -> 1.57 ; '1513,0' -> 1513.0 ; '-' -> None."""
    s = s.strip().replace(" ", "")
    if s in ("", "-"):
        return None
    if "," in s:
        return float(s.replace(".", "").replace(",", "."))
    return int(s.replace(".", ""))


def fmt_int(v):
    return "–" if v is None else f"{v:,.0f}".replace(",", ".")


def fmt_mil(v):
    return "–" if v is None else f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".") + "&nbsp;mil"


def fmt_pct(v):
    if v is None:
        return f'<span style="color:{MUTED}">–</span>'
    cor = UP if v > 0 else DOWN if v < 0 else INK
    seta = "▲" if v > 0 else "▼" if v < 0 else ""
    txt = f"{v:+.1f}%".replace(".", ",")
    return f'<span style="color:{cor};font-weight:700;white-space:nowrap">{seta}&nbsp;{txt}</span>'


def pct_txt(v):
    return "–" if v is None else f"{v:+.1f}%".replace(".", ",")


# ---------------------------------------------------------------- rede
def session():
    s = requests.Session()
    s.headers.update(BROWSER_HEADERS)
    return s


def get_pdf_text(s, url, pages):
    r = s.get(url, timeout=90)
    r.raise_for_status()
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        return [(p.extract_text() or "") for p in pdf.pages[:pages]]


# ---------------------------------------------------------------- FENABRAVE
FEN_ROWS = [
    ("A) Autos", "Automóveis"),
    ("B) Com. Leves", "Comerciais leves"),
    ("A + B", "Autos + comerciais leves"),
    ("C) Caminhões", "Caminhões"),
    ("D) Ônibus", "Ônibus"),
    ("C + D", "Caminhões + ônibus"),
    ("Subtotal", "Subtotal (autoveículos)"),
    ("E) Motos", "Motos"),
    ("F) Impl. Rod.", "Implementos rodoviários"),
    ("Outros", "Outros"),
]
NUM = r"(-?[\d\.]+(?:,\d+)?|-)"


def fenabrave_latest(s):
    """Último PDF do Informativo: links /portal/files/AAAA_MM_xx.pdf."""
    try:
        s.get(FENABRAVE_HOME, timeout=30)
    except Exception:
        pass
    r = s.get(FENABRAVE_PAGE, timeout=40)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    best = None
    for a in soup.find_all("a", href=True):
        m = re.search(r"/portal/files/(\d{4})_(\d{2})_\d+\.pdf$", a["href"], re.I)
        if m:
            key = (int(m.group(1)), int(m.group(2)))
            if best is None or key > best[0]:
                best = (key, requests.compat.urljoin(FENABRAVE_PAGE, a["href"]))
    return best[1] if best else None


def parse_fenabrave(text):
    """Página 1 do Informativo: Resumo Mensal por segmento.
    Colunas: A=mês, B=mês anterior, C=acumulado, D=mesmo mês ano anterior,
    E=acumulado ano anterior, A/B, A/D, C/E (%)."""
    m = re.search(r"Resumo Mensal\s+(\w+)\s+de\s+(\d{4})", text, re.I)
    periodo = f"{m.group(1).capitalize()}/{m.group(2)}" if m else ""
    linhas = []
    for chave, nome in FEN_ROWS:
        pat = re.escape(chave) + r"\s+" + r"\s+".join([NUM] * 8) + r"\s*$"
        mm = re.search(pat, text, re.M)
        if not mm:
            continue
        v = [num(x) for x in mm.groups()]
        linhas.append({"segmento": nome, "mes": v[0], "mes_ant": v[1], "acum": v[2],
                       "mes_aa": v[3], "acum_aa": v[4], "mm": v[5], "aa": v[6], "acum_var": v[7]})
    por_nome = {l["segmento"]: l for l in linhas}
    partes = [por_nome.get(n) for n in ("Subtotal (autoveículos)", "Motos", "Implementos rodoviários", "Outros")]
    if all(partes):
        t = {k: sum(p[k] for p in partes) for k in ("mes", "mes_ant", "acum", "mes_aa", "acum_aa")}
        var = lambda a, b: (a / b - 1) * 100 if b else None
        t.update(segmento="Total geral", mm=var(t["mes"], t["mes_ant"]),
                 aa=var(t["mes"], t["mes_aa"]), acum_var=var(t["acum"], t["acum_aa"]))
        linhas.append(t)
    return {"periodo": periodo, "linhas": linhas}


def html_fenabrave(d, url):
    headers = ["Segmento", "Mês", "Mês ant.", "Var. m/m", "Mês ano ant.", "Var. a/a",
               "Acum. ano", "Acum. ano ant.", "Var. acum."]
    destaque = {"Subtotal (autoveículos)", "Total geral"}
    rows = []
    for l in d["linhas"]:
        b = (lambda x: f"<b>{x}</b>") if l["segmento"] in destaque else (lambda x: x)
        rows.append([b(esc(l["segmento"])), b(fmt_int(l["mes"])), fmt_int(l["mes_ant"]), fmt_pct(l["mm"]),
                     fmt_int(l["mes_aa"]), fmt_pct(l["aa"]), b(fmt_int(l["acum"])), fmt_int(l["acum_aa"]),
                     fmt_pct(l["acum_var"])])
    return (section_title(f"FENABRAVE · Emplacamentos · {d['periodo']}")
            + resumo_fenabrave(d)
            + data_table(headers, rows)
            + row(f'<span style="font:12px {FONT};color:{MUTED}">Fonte: FENABRAVE, Informativo – Emplacamentos. '
                  f'Unidades. Var. m/m = sobre o mês anterior; a/a = sobre o mesmo mês do ano anterior.</span>')
            + button(url, "Abrir PDF da FENABRAVE"))


def resumo_fenabrave(d):
    t = next((l for l in d["linhas"] if l["segmento"] == "Total geral"), None)
    a = next((l for l in d["linhas"] if l["segmento"] == "Autos + comerciais leves"), None)
    partes = []
    if t:
        partes.append(f"Total de <b>{fmt_int(t['mes'])}</b> unidades: {fmt_pct(t['mm'])} no mês, "
                      f"{fmt_pct(t['aa'])} contra o ano anterior e {fmt_pct(t['acum_var'])} no acumulado do ano.")
    if a:
        partes.append(f"Autos + comerciais leves: <b>{fmt_int(a['mes'])}</b> ({fmt_pct(a['aa'])} a/a).")
    return row(" ".join(partes)) if partes else ""


def texto_fenabrave(d):
    linhas = [f"FENABRAVE - Emplacamentos {d['periodo']}",
              f"{'Segmento':28} {'Mês':>10} {'m/m':>8} {'a/a':>8} {'Acum.':>12} {'Acum.%':>8}"]
    for l in d["linhas"]:
        linhas.append(f"{l['segmento'][:28]:28} {fmt_int(l['mes']):>10} {pct_txt(l['mm']):>8} "
                      f"{pct_txt(l['aa']):>8} {fmt_int(l['acum']):>12} {pct_txt(l['acum_var']):>8}")
    return "\n".join(linhas)


# ---------------------------------------------------------------- ANFAVEA
def anfavea_latest(s):
    """Carta mais recente: links .../cartas/cartaNNN.pdf. Retorna (número, url, rótulo do link).
    A ANFAVEA às vezes troca o conteúdo do mesmo cartaNNN.pdf; o rótulo (ex.: "Setembro/2026") avisa."""
    r = s.get(ANFAVEA_PAGE, timeout=40)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    best = None
    for a in soup.find_all("a", href=True):
        m = re.search(r"cartas?/carta(\d+)\.pdf$", a["href"], re.I)
        if m and (best is None or int(m.group(1)) > best[0]):
            best = (int(m.group(1)), requests.compat.urljoin(ANFAVEA_PAGE, a["href"]), a.get_text(" ", strip=True))
    return best


MIL = r"(-?[\d\.]+(?:,\d+)?)\s*mil"
PCT = r"(-?[\d\.]+(?:,\d+)?)\s*%"


def parse_resumo_anfavea(text):
    """Página 1 da Carta: três colunas (emplacamento, exportação, produção).
    Linhas com 3 valores em 'mil': mês, mês anterior, mesmo mês ano anterior,
    acumulado, acumulado ano anterior. Linhas com 3 '%': m/m, a/a, acumulado."""
    mils, pcts = [], []
    for ln in text.splitlines():
        v = re.findall(MIL, ln)
        if len(v) == 3:
            mils.append([num(x) for x in v])
            continue
        p = re.findall(PCT, ln)
        if len(p) == 3:
            pcts.append([num(x) for x in p])
    if len(mils) < 5 or len(pcts) < 3:
        return []
    out = []
    for i, nome in enumerate(["Emplacamento", "Exportação", "Produção"]):
        out.append({"indicador": nome, "mes": mils[0][i], "mes_ant": mils[1][i], "mes_aa": mils[2][i],
                    "acum": mils[3][i], "acum_aa": mils[4][i],
                    "mm": pcts[0][i], "aa": pcts[1][i], "acum_var": pcts[2][i]})
    return out


ANF_SEG = [
    (r"Unidades - Total", "Total"),
    (r"Automóveis / Automobiles", "Automóveis"),
    (r"Comerciais leves / Light", "Comerciais leves"),
    (r"Caminhões / Trucks", "Caminhões"),
]
ANF_NUM = r"(-?[\d\.]+(?:,\d+)?|-)"


def parse_segmentos_anfavea(text):
    """Tabela 'Emplacamento total de autoveículos novos - nacionais e importados':
    A=mês, B=mês anterior, C=acumulado, D=mesmo mês ano anterior, E=acumulado ano
    anterior, A/B, A/D, C/E (%). A linha de ônibus vem sem rótulo logo após Pesados."""
    i = text.find("Emplacamento total de autoveículos novos")
    if i < 0:
        return []
    bloco = text[i:]
    fim = bloco.find("mil unidades")
    bloco = bloco[:fim] if fim > 0 else bloco
    cols = r"\s+".join([ANF_NUM] * 8)
    out = []
    for rotulo, nome in ANF_SEG:
        m = re.search(rotulo + r".*?\s" + cols + r"\s*$", bloco, re.M)
        if m:
            out.append((nome, [num(x) for x in m.groups()]))
    m = re.search(r"^Pesados.*$\n^" + cols + r"\s*$", bloco, re.M)
    if m:
        out.append(("Ônibus", [num(x) for x in m.groups()]))
    return [{"segmento": n, "mes": v[0], "mes_ant": v[1], "acum": v[2], "mes_aa": v[3], "acum_aa": v[4],
             "mm": v[5], "aa": v[6], "acum_var": v[7]} for n, v in out]


def parse_anfavea(pages):
    p1 = pages[0] if pages else ""
    m = re.search(r"Resultados de (\w+) de (\d{4})", p1, re.I) or re.search(r"RESULTADOS\s+(\w+)\s+(\d{4})", p1)
    periodo = f"{m.group(1).capitalize()}/{m.group(2)}" if m else ""
    seg_page = next((p for p in pages if "Emplacamento total de autoveículos novos" in p), "")
    return {"periodo": periodo, "resumo": parse_resumo_anfavea(p1), "segmentos": parse_segmentos_anfavea(seg_page)}


def html_anfavea(d, url):
    col = d.get("aprox")
    out = section_title(f"ANFAVEA · {'Coletiva de imprensa' if col else 'Carta'} · {d['periodo']}")
    if d["resumo"]:
        e = d["resumo"][0]
        p = d["resumo"][2]
        out += row(f"Emplacamento de <b>{fmt_mil(e['mes'])}</b> ({fmt_pct(e['aa'])} a/a); "
                   f"produção de <b>{fmt_mil(p['mes'])}</b> ({fmt_pct(p['aa'])} a/a).")
        headers = ["Autoveículos", "Mês", "Mês ant.", "Var. m/m", "Mês ano ant.", "Var. a/a",
                   "Acum. ano", "Acum. ano ant.", "Var. acum."]
        rows = [[f"<b>{esc(l['indicador'])}</b>", f"<b>{fmt_mil(l['mes'])}</b>", fmt_mil(l["mes_ant"]),
                 fmt_pct(l["mm"]), fmt_mil(l["mes_aa"]), fmt_pct(l["aa"]), fmt_mil(l["acum"]),
                 fmt_mil(l["acum_aa"]), fmt_pct(l["acum_var"])] for l in d["resumo"]]
        out += data_table(headers, rows)
    if d["segmentos"]:
        out += section_title("ANFAVEA · Emplacamento por segmento (nacionais + importados)")
        headers = ["Segmento", "Mês", "Mês ant.", "Var. m/m", "Mês ano ant.", "Var. a/a",
                   "Acum. ano", "Acum. ano ant.", "Var. acum."]
        rows = []
        for l in d["segmentos"]:
            b = (lambda x: f"<b>{x}</b>") if l["segmento"] == "Total" else (lambda x: x)
            rows.append([b(esc(l["segmento"])), b(fmt_int(l["mes"])), fmt_int(l["mes_ant"]), fmt_pct(l["mm"]),
                         fmt_int(l["mes_aa"]), fmt_pct(l["aa"]), b(fmt_int(l["acum"])), fmt_int(l["acum_aa"]),
                         fmt_pct(l["acum_var"])])
        out += data_table(headers, rows)
    if d.get("projecoes"):
        out += section_title("ANFAVEA · Projeções 2026 revisadas (mil unidades)")
        rows = [[f"<b>{esc(l['indicador'])}</b>", fmt_mil(l["ano_ant"]), fmt_mil(l["anterior"]),
                 f"<b>{fmt_mil(l['nova'])}</b>", fmt_pct(l["var"])] for l in d["projecoes"]]
        out += data_table(["Indicador", "Ano anterior", "Projeção anterior", "Nova projeção", "Var. s/ ano ant."], rows)
    fonte = ("Fonte: ANFAVEA, apresentação da coletiva de imprensa. A Carta da Anfavea com os números exatos "
             "ainda não saiu; por segmento, as unidades são aproximadas (slide em mil, uma casa) e serão "
             "trocadas pelas da Carta quando ela sair." if col else "Fonte: ANFAVEA, Carta da Anfavea.")
    out += row(f'<span style="font:12px {FONT};color:{MUTED}">{fonte} '
               f'Var. m/m = sobre o mês anterior; a/a = sobre o mesmo mês do ano anterior.</span>')
    return out + button(url, "Abrir apresentação da coletiva" if col else "Abrir Carta da ANFAVEA")


# ------------------------------------------- ANFAVEA: coletiva de imprensa
# A coletiva (apresentação em PDF) sai no dia da divulgação; a Carta às vezes
# atrasa. Quando a coletiva traz um mês mais novo que o último guardado, os
# números saem dela: cada valor (em mil, uma casa) só é aceito se bater com as
# variações impressas no slide (mês/mês, ano/ano e acumulado) e com o
# acumulado do mês anterior já guardado. Quando a Carta do mesmo mês sair, ela
# substitui estes números sem mandar outro e-mail.

def mes_idx(periodo):
    """'Setembro/2026' -> 2026*12+9 ; vazio -> 0."""
    m = re.match(r"(\w+)/(\d{4})", periodo or "")
    if not m or m.group(1).lower() not in MESES:
        return 0
    return int(m.group(2)) * 12 + MESES.index(m.group(1).lower()) + 1


def anfavea_coletiva(s):
    """Coletiva mais recente na página inicial. Retorna (url do PDF, url da página, url do release) ou None."""
    r = s.get(ANFAVEA_HOME, timeout=40)
    r.raise_for_status()
    best = None
    for a in BeautifulSoup(r.text, "html.parser").find_all("a", href=True):
        m = re.search(r"coletiva-de-imprensa-(\w+)-(\d{4})/?$", a["href"], re.I)
        if m and m.group(1).lower() in MESES:
            k = int(m.group(2)) * 12 + MESES.index(m.group(1).lower())
            if best is None or k > best[0]:
                best = (k, requests.compat.urljoin(ANFAVEA_HOME, a["href"]))
    if not best:
        return None
    r = s.get(best[1], timeout=40)
    r.raise_for_status()
    pdf = release = None
    for a in BeautifulSoup(r.text, "html.parser").find_all("a", href=True):
        h = a["href"]
        if not h.lower().endswith(".pdf"):
            continue
        if re.search(r"release", h, re.I):
            release = release or h
        elif re.search(r"coletiva", h + a.get_text(" "), re.I):
            pdf = pdf or h
    return (pdf, best[1], release) if pdf else None


RE_VAR = re.compile(r"(?:\b(\w{3})\s+)?(\d{2})\s*vs\.\s*(?:(\w{3})\s+)?(\d{2})\s*:\s*([+-])\s*(\d+(?:,\d+)?)\s*%")
RE_TOK = re.compile(r"(?<![\d,.])\d{1,3}(?:\.\d{3})*(?:,\d+)?(?![\d%])")


def _pagina(pages, *titulos, sem=("VARIAÇÃO", "Média diária", "Acumulado")):
    for t in pages:
        cab = " ".join(t.split("\n")[:3])
        if all(x in cab for x in titulos) and not any(x in t for x in sem):
            return t
    return ""


def _variacoes(texto):
    """Trios (m/m, a/a, acumulado) na ordem em que aparecem no slide."""
    grupos, g = [], {}
    for m1, a1, m2, a2, sinal, v in RE_VAR.findall(texto):
        v = num(v) * (-1 if sinal == "-" else 1)
        tipo = "acum" if not m1 else "aa" if m1.lower() == (m2 or "").lower() else "mm"
        g[tipo] = v
        if len(g) == 3:
            grupos.append(g)
            g = {}
    return grupos


def _tokens(texto):
    out = []
    for ln in texto.splitlines():
        if "vs." in ln or "%" in ln or "Fonte" in ln:
            continue
        for t in RE_TOK.findall(ln):
            v = num(t)
            if isinstance(v, float) or v >= 10:
                out.append(float(v))
    return out


def _resolve(tokens, var, ant):
    """Acha no slide o valor do mês (X) e o do mesmo mês do ano anterior (Y), em mil,
    conferindo com as variações. ant: mês anterior / acumulados anteriores, em mil."""
    melhor = None
    for x in set(tokens):
        if abs(x - ant["mes"] * (1 + var["mm"] / 100)) > 0.06 + 0.001 * x:
            continue
        for y in set(tokens):
            if abs(x / (1 + var["aa"] / 100) - y) > 0.08 + 0.001 * x:
                continue
            ac, ac_aa = ant["acum"] + x, ant["acum_aa"] + y
            erro = abs((ac / ac_aa - 1) * 100 - var["acum"])
            if erro < 0.3 and (melhor is None or erro < melhor[2]):
                melhor = (x, y, erro)
    return melhor


def parse_coletiva(pages, antes):
    """Monta resumo + segmentos (mesmo formato da Carta) a partir da coletiva e do mês anterior guardado."""
    m = re.search(r"\|\s*([A-ZÇ]+)\s+(\d{4})", pages[0] if pages else "")
    periodo = f"{m.group(1).capitalize()}/{m.group(2)}" if m else ""
    if not periodo or mes_idx(periodo) != mes_idx(antes.get("periodo")) + 1:
        return None
    resumo, falhas = [], []
    for nome, titulos in [("Emplacamento", ("EMPLACAMENTO", "AUTOVEÍCULOS")),
                          ("Exportação", ("EXPORTAÇÃO", "AUTOVEÍCULOS EXPORTADOS")),
                          ("Produção", ("PRODUÇÃO", "AUTOVEÍCULOS"))]:
        t = _pagina(pages, *titulos)
        a = next((l for l in antes.get("resumo", []) if l["indicador"] == nome), None)
        g = _variacoes(t)
        r = _resolve(_tokens(t), g[0], a) if (t and a and g) else None
        if not r:
            falhas.append(nome)
            continue
        x, y, _ = r
        resumo.append({"indicador": nome, "mes": x, "mes_ant": a["mes"], "mes_aa": y,
                       "acum": round(a["acum"] + x, 1), "acum_aa": round(a["acum_aa"] + y, 1),
                       "mm": g[0]["mm"], "aa": g[0]["aa"], "acum_var": g[0]["acum"]})
    segs = {l["segmento"]: l for l in antes.get("segmentos", [])}
    slides = [("Total", _pagina(pages, "EMPLACAMENTO", "AUTOVEÍCULOS"), 0),
              ("Automóveis", _pagina(pages, "EMPLACAMENTO", "VEÍCULOS LEVES"), 0),
              ("Comerciais leves", _pagina(pages, "EMPLACAMENTO", "VEÍCULOS LEVES"), 1),
              ("Caminhões", _pagina(pages, "EMPLACAMENTO", "VEÍCULOS PESADOS"), 0),
              ("Ônibus", _pagina(pages, "EMPLACAMENTO", "VEÍCULOS PESADOS"), 1)]
    segmentos = []
    for nome, t, i in slides:
        a, g = segs.get(nome), _variacoes(t)
        if not a or len(g) <= i:
            continue
        mil = {k: a[k] / 1000 for k in ("mes", "acum", "acum_aa")}
        r = _resolve(_tokens(t), g[i], mil)
        if not r:
            falhas.append(nome)
            continue
        x, y, _ = r
        # unidades: parte do mês anterior exato e da variação, sem sair do valor arredondado do slide
        mes = round(min(max(a["mes"] * (1 + g[i]["mm"] / 100), x * 1000 - 50), x * 1000 + 50))
        mes_aa = round(min(max(mes / (1 + g[i]["aa"] / 100), y * 1000 - 50), y * 1000 + 50))
        segmentos.append({"segmento": nome, "mes": mes, "mes_ant": a["mes"], "acum": a["acum"] + mes,
                          "mes_aa": mes_aa, "acum_aa": a["acum_aa"] + mes_aa,
                          "mm": g[i]["mm"], "aa": g[i]["aa"], "acum_var": g[i]["acum"]})
    proj = []
    t = next((x for x in pages if "REVISÃO DAS PROJEÇÕES" in x), "")
    for m in re.finditer(r"(Emplacamento|Exportação|Produção)\s+([\d.,]+)\s+([\d.,]+)\s+([+-]?[\d,]+)%\s+([\d.,]+)\s+([+-]?[\d,]+)%", t):
        proj.append({"indicador": m.group(1), "ano_ant": num(m.group(2)), "anterior": num(m.group(3)),
                     "nova": num(m.group(5)), "var": num(m.group(6))})
    if len(resumo) < 3:
        print(f"[AVISO] ANFAVEA coletiva {periodo}: não bateu {', '.join(falhas)}.")
        return None
    return {"periodo": periodo, "resumo": resumo, "segmentos": segmentos, "projecoes": proj, "aprox": True}


def texto_anfavea(d):
    mil = lambda v: fmt_mil(v).replace("&nbsp;", " ")
    linhas = [f"ANFAVEA - {'Coletiva' if d.get('aprox') else 'Carta'} {d['periodo']}",
              f"{'Indicador':14} {'Mês':>12} {'m/m':>8} {'a/a':>8} {'Acum.':>14} {'Acum.%':>8}"]
    for l in d["resumo"]:
        linhas.append(f"{l['indicador']:14} {mil(l['mes']):>12} {pct_txt(l['mm']):>8} {pct_txt(l['aa']):>8} "
                      f"{mil(l['acum']):>14} {pct_txt(l['acum_var']):>8}")
    if d["segmentos"]:
        linhas.append("")
        linhas.append("Emplacamento por segmento")
        for l in d["segmentos"]:
            linhas.append(f"{l['segmento']:18} {fmt_int(l['mes']):>10} {pct_txt(l['mm']):>8} {pct_txt(l['aa']):>8} "
                          f"{fmt_int(l['acum']):>12} {pct_txt(l['acum_var']):>8}")
    if d.get("projecoes"):
        linhas.append("")
        linhas.append("Projeções 2026 revisadas (mil)")
        for l in d["projecoes"]:
            linhas.append(f"{l['indicador']:14} {fmt_int(l['anterior']):>8} -> {fmt_int(l['nova']):>8} ({pct_txt(l['var'])} s/ ano ant.)")
    return "\n".join(linhas)


# ---------------------------------------------------------------- principal
def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="não envia; salva alerts/setor_preview.html")
    ap.add_argument("--force", action="store_true", help="reenvia o último relatório de cada fonte")
    args = ap.parse_args()

    BASE.mkdir(exist_ok=True)
    state = load_state()
    s = session()
    erros = []

    # FENABRAVE
    try:
        url = fenabrave_latest(s)
        if not url:
            erros.append("FENABRAVE: nenhum PDF encontrado na página de emplacamentos.")
        elif url != state.get("fenabrave", {}).get("url") or args.force:
            d = parse_fenabrave(get_pdf_text(s, url, 1)[0])
            if len(d["linhas"]) < 5:
                erros.append(f"FENABRAVE: não consegui ler a tabela do PDF {url}.")
            else:
                print(texto_fenabrave(d))
                subject = f"FENABRAVE: emplacamentos de {d['periodo']} em tabela"
                html = page("FENABRAVE · RELATÓRIO MENSAL", f"Emplacamentos {d['periodo']}",
                            "Resumo por segmento com variações", html_fenabrave(d, url),
                            "Enviado automaticamente pelo monitor ANFAVEA/FENABRAVE.")
                if args.dry_run:
                    PREVIEW_FILE.with_name("setor_preview_fenabrave.html").write_text(html, encoding="utf-8")
                else:
                    send_email(subject, texto_fenabrave(d) + f"\n\nPDF: {url}", html)
                    print("[INFO] E-mail FENABRAVE enviado.")
                state["fenabrave"] = {"url": url, "periodo": d["periodo"], "linhas": d["linhas"]}
                monitoramento.add_event(state, "FENABRAVE", f"Emplacamentos de {d['periodo']} — tabela por segmento", url)
        else:
            print(f"[OK] FENABRAVE sem relatório novo ({state['fenabrave'].get('periodo')}).")
    except Exception as exc:
        erros.append(f"FENABRAVE: {exc}")

    # ANFAVEA
    try:
        latest = anfavea_latest(s)
        antes = state.get("anfavea", {})
        if not latest:
            erros.append("ANFAVEA: nenhuma Carta encontrada.")
        elif (latest[0] != antes.get("carta") or latest[2] != antes.get("rotulo")
              or antes.get("fonte") == "coletiva" or args.force):
            numero, url, rotulo = latest
            d = parse_anfavea(get_pdf_text(s, url, 6))
            if antes.get("fonte") == "coletiva" and d["periodo"] == antes.get("periodo") and d["resumo"] and not args.force:
                # a Carta do mês que veio pela coletiva saiu: troca pelos números exatos, sem outro e-mail
                state["anfavea"] = {"carta": numero, "url": url, "periodo": d["periodo"], "rotulo": rotulo,
                                    "resumo": d["resumo"], "segmentos": d["segmentos"],
                                    "projecoes": antes.get("projecoes", []), "coletiva_url": antes.get("coletiva_url")}
                monitoramento.add_event(state, "ANFAVEA", f"Carta {numero} — números exatos de {d['periodo']}", url)
                print(f"[INFO] ANFAVEA: Carta {numero} substituiu os números da coletiva ({d['periodo']}).")
            elif mes_idx(d["periodo"]) < mes_idx(antes.get("periodo")) and not args.force:
                print(f"[OK] ANFAVEA: Carta {numero} ainda com {d['periodo']}; {antes.get('periodo')} veio da coletiva.")
            elif numero == antes.get("carta") and d["periodo"] == antes.get("periodo") and not args.force:
                # mesmo número e mesmo mês no PDF: só o rótulo mudou (ou o PDF ainda não foi trocado)
                print(f"[OK] ANFAVEA: Carta {numero} ainda com {d['periodo']} (rótulo do site: {rotulo}).")
                state["anfavea"]["rotulo"] = rotulo if d["periodo"].lower() in rotulo.lower() else antes.get("rotulo")
            elif not d["resumo"] and not d["segmentos"]:
                erros.append(f"ANFAVEA: não consegui ler as tabelas da Carta {numero} ({url}).")
            else:
                print(texto_anfavea(d))
                subject = f"ANFAVEA: resultados de {d['periodo']} em tabela (Carta {numero})"
                html = page("ANFAVEA · CARTA MENSAL", f"Resultados {d['periodo']}",
                            f"Carta da Anfavea nº {numero}", html_anfavea(d, url),
                            "Enviado automaticamente pelo monitor ANFAVEA/FENABRAVE.")
                if args.dry_run:
                    PREVIEW_FILE.with_name("setor_preview_anfavea.html").write_text(html, encoding="utf-8")
                else:
                    send_email(subject, texto_anfavea(d) + f"\n\nPDF: {url}", html)
                    print("[INFO] E-mail ANFAVEA enviado.")
                state["anfavea"] = {"carta": numero, "url": url, "periodo": d["periodo"], "rotulo": rotulo,
                                    "resumo": d["resumo"], "segmentos": d["segmentos"],
                                    "coletiva_url": antes.get("coletiva_url")}
                monitoramento.add_event(state, "ANFAVEA", f"Carta {numero} — resultados de {d['periodo']}", url)
        else:
            print(f"[OK] ANFAVEA sem Carta nova ({state['anfavea'].get('periodo')}).")
    except Exception as exc:
        erros.append(f"ANFAVEA: {exc}")

    # ANFAVEA pela coletiva, quando ela traz um mês que a Carta ainda não trouxe
    try:
        antes = state.get("anfavea", {})
        col = anfavea_coletiva(s)
        if col and (col[0] != antes.get("coletiva_url") or args.force):
            url, pagina, release = col
            pages = get_pdf_text(s, url, 30)
            d = parse_coletiva(pages, antes)
            if d is None and mes_idx(antes.get("periodo")) and re.search(r"\|\s*([A-ZÇ]+)\s+(\d{4})", pages[0] or ""):
                m = re.search(r"\|\s*([A-ZÇ]+)\s+(\d{4})", pages[0])
                if mes_idx(f"{m.group(1).capitalize()}/{m.group(2)}") > mes_idx(antes.get("periodo")):
                    erros.append(f"ANFAVEA: não consegui ler os números da coletiva ({url}).")
            if d:
                print(texto_anfavea(d))
                subject = f"ANFAVEA: resultados de {d['periodo']} em tabela (coletiva de imprensa)"
                html = page("ANFAVEA · COLETIVA MENSAL", f"Resultados {d['periodo']}",
                            "Coletiva de imprensa da Anfavea (a Carta ainda não saiu)", html_anfavea(d, url),
                            "Enviado automaticamente pelo monitor ANFAVEA/FENABRAVE.")
                if args.dry_run:
                    PREVIEW_FILE.with_name("setor_preview_anfavea.html").write_text(html, encoding="utf-8")
                else:
                    send_email(subject, texto_anfavea(d) + f"\n\nApresentação: {url}" +
                               (f"\nRelease: {release}" if release else ""), html)
                    print("[INFO] E-mail ANFAVEA (coletiva) enviado.")
                state["anfavea"] = {"carta": antes.get("carta"), "rotulo": antes.get("rotulo"), "url": url,
                                    "periodo": d["periodo"], "fonte": "coletiva", "release": release,
                                    "resumo": d["resumo"], "segmentos": d["segmentos"], "projecoes": d["projecoes"]}
                monitoramento.add_event(state, "ANFAVEA", f"Coletiva — resultados de {d['periodo']} (Carta ainda não saiu)", url)
            if not args.dry_run:
                state.setdefault("anfavea", {})["coletiva_url"] = url
        elif col:
            print("[OK] ANFAVEA: coletiva já lida.")
    except Exception as exc:
        erros.append(f"ANFAVEA coletiva: {exc}")

    if not args.dry_run:
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        monitoramento.write()
    for e in erros:
        print(f"[ERRO] {e}", file=sys.stderr)
    if erros:
        sys.exit(1)


if __name__ == "__main__":
    main()
