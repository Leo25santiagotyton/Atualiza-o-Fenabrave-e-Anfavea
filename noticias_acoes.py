"""
Boletim de notícias materiais das ações B3
------------------------------------------
Roda todo dia às 8h30 e às 19h (via GitHub Actions). Busca notícias das
empresas no Google News e os documentos entregues à CVM (fato relevante, comunicado
ao mercado, aviso aos acionistas), mantém só as que podem mexer com a ação (resultado,
M&A, dívida e rating, proventos, gestão, regulatório, recomendação de
analistas, contratos relevantes), monta um resumo do mercado e envia por e-mail.

Também grava alerts/news.json, que alimenta a faixa de notícias do painel
publicado no claude.ai.

São dois e-mails por horário: um das ações na B3 e outro dos bonds em US$. No de bonds
só entram os emissores sem ação na B3 (OHI, Borr, Foresea, Constellation, CHC); as
notícias de bonds de Movida, Simpar, Vamos e Tupy vão para o e-mail das ações.

E-mail via as mesmas variáveis do monitor:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM, EMAIL_TO

Uso:
  python noticias_acoes.py              # busca, grava e envia
  python noticias_acoes.py --dry-run    # não envia; salva alerts/news_preview.html
  python noticias_acoes.py --no-email   # só atualiza as notícias do painel
"""

import argparse
import hashlib
import html
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus

import requests

from alerta_acoes import BRT, DASHBOARD_URL, HEADERS, br, send_email

OUT_DIR = Path(__file__).parent / "alerts"
NEWS_FILE = OUT_DIR / "news.json"
STATE_FILE = OUT_DIR / "news_state.json"
KEEP_ITEMS = 150          # quantas notícias o painel guarda
SEEN_DAYS = 10            # por quanto tempo lembrar o que já foi enviado

# ticker(s) -> empresa, busca no Google News e padrão que confirma a menção no título.
# O padrão diferencia maiúsculas para não confundir o nome com palavras comuns
# ("localiza", "movida", "vamos").
COMPANIES = [
    {"tickers": ["MOVI3"], "name": "Movida", "cvm": r"^MOVIDA",
     "query": '"Movida" (locadora OR MOVI3 OR ações OR aluguel OR carros) OR MOVI3',
     "match": r"\bMovida\b|MOVI3"},
    {"tickers": ["SIMH3"], "name": "Simpar", "cvm": r"^SIMPAR",
     "query": "Simpar OR SIMH3", "match": r"\bSimpar\b|\bSIMPAR\b|SIMH3"},
    {"tickers": ["VAMO3"], "name": "Vamos", "cvm": r"^VAMOS LOCA",
     "query": '"Grupo Vamos" OR "Vamos Locação" OR VAMO3',
     "match": r"Grupo Vamos|Vamos Loca|VAMO3"},
    {"tickers": ["JSLG3"], "name": "JSL", "cvm": r"^JSL\b",
     "query": 'JSLG3 OR "JSL" logística OR "JSL S.A."', "match": r"\bJSL\b|JSLG3"},
    {"tickers": ["AMOB3"], "name": "Automob", "cvm": r"^AUTOMOB",
     "query": "Automob OR AMOB3", "match": r"\bAutomob\b|AMOB3"},
    {"tickers": ["RAPT3", "RAPT4"], "name": "Randoncorp", "cvm": r"^RANDON",
     "query": "Randoncorp OR Randon OR RAPT4 OR RAPT3", "match": r"\bRandon(corp)?\b|RAPT[34]"},
    {"tickers": ["RENT3"], "name": "Localiza", "cvm": r"^LOCALIZA RENT",
     "query": "Localiza OR RENT3", "match": r"\bLocaliza\b|RENT3"},
    {"tickers": ["FRAS3"], "name": "Frasle Mobility", "cvm": r"^FRAS.?LE",
     "query": 'Frasle OR "Fras-le" OR FRAS3', "match": r"\bFras-?le\b|\bFrasle\b|FRAS3"},
    {"tickers": ["ARML3"], "name": "Armac", "cvm": r"^ARMAC",
     "query": "Armac OR ARML3", "match": r"\bArmac\b|ARML3"},
    {"tickers": ["PRNR3"], "name": "Priner", "cvm": r"^PRINER",
     "query": "Priner OR PRNR3", "match": r"\bPriner\b|PRNR3"},
    {"tickers": ["TUPY3"], "name": "Tupy", "cvm": r"^TUPY",
     "query": "Tupy OR TUPY3", "match": r"\bTupy\b|TUPY3"},
]

# emissores de bonds em US$ (aba Bond do painel): notícias de dívida, rating, resultado e eventos de crédito
BOND_TERMS = '(bond OR bonds OR notes OR "senior notes" OR rating OR Fitch OR Moody\'s OR "S&P" OR dívida OR debt OR tender OR recompra OR resultado OR earnings OR refinanciamento OR refinancing)'
BOND_ISSUERS = [
    {"name": "Simpar", "bond": "Simpar Europe 2031", "query": f'(Simpar OR "Simpar Europe") {BOND_TERMS}', "match": r"\bSimpar\b"},
    {"name": "Movida", "bond": "Movida Europe 2029/2031/2033", "query": f'(Movida OR "Movida Europe") {BOND_TERMS}', "match": r"\bMovida\b"},
    {"name": "Vamos", "bond": "Vamos Europe 2031", "query": f'("Grupo Vamos" OR "Vamos Locação" OR "Vamos Europe" OR VAMO3) {BOND_TERMS}', "match": r"Grupo Vamos|Vamos Loca|Vamos Europe|VAMO3|\bVamos\b.*(bond|rating|notes|dívida)"},
    {"name": "OHI Group", "bond": "OHI 2029", "query": f'("OHI Group" OR "OHI S.A.") {BOND_TERMS}', "match": r"\bOHI\b"},
    {"name": "Borr Drilling", "bond": "Borr IHC 2032", "query": f'("Borr Drilling" OR "Borr IHC") {BOND_TERMS}', "match": r"\bBorr\b"},
    {"name": "Foresea", "bond": "Foresea 2030", "query": f'(Foresea OR "Foresea Holding") {BOND_TERMS}', "match": r"\bForesea\b"},
    {"name": "Constellation", "bond": "Constellation 2033", "query": f'("Constellation Oil" OR "Constellation Oil Services" OR "Constellation Serviços") {BOND_TERMS}', "match": r"Constellation"},
    {"name": "Tupy", "bond": "Tupy Overseas 2031", "query": f'(Tupy OR "Tupy Overseas") {BOND_TERMS}', "match": r"\bTupy\b"},
    {"name": "CHC Group", "bond": "CHC 2030", "query": f'("CHC Group" OR "CHC Helicopter") {BOND_TERMS}', "match": r"\bCHC\b"},
]
BOND_KEEP = 150
# páginas de cotação e cadastros financeiros que o Google News devolve como notícia
BOND_NOISE = re.compile(r"stock price|price, news|quote & history|cota[cç][aã]o e hist[oó]rico|balance sheet|balan[cç]o patrimonial|"
                        r"income statement|cash flow statement|depository receipts|\bshs\b|market cap|share price today", re.I)
# emissores com ação na B3: notícias de bond vão para o e-mail das ações, não para o de bonds
BOND_LISTED = {"Simpar": ["SIMH3"], "Movida": ["MOVI3"], "Vamos": ["VAMO3"], "Tupy": ["TUPY3"]}
BONDS_FILE = OUT_DIR / "bonds.json"


def translate_pt(session, text):
    """Tradução en → pt da manchete: Google Tradutor (gratuito) e, se bloquear, MyMemory; None se ambos falharem."""
    try:
        r = session.get("https://translate.googleapis.com/translate_a/single",
                        params={"client": "gtx", "sl": "en", "tl": "pt", "dt": "t", "q": text}, timeout=15)
        if r.ok and r.headers.get("content-type", "").startswith(("application/json", "text/javascript")):
            out = "".join(part[0] for part in r.json()[0] if part and part[0]).strip()
            if out:
                return out
    except Exception:
        pass
    try:
        r = session.get("https://api.mymemory.translated.net/get", params={"q": text[:480], "langpair": "en|pt-BR"}, timeout=20)
        j = r.json()
        out = html.unescape((j.get("responseData") or {}).get("translatedText") or "").strip()
        if out and j.get("responseStatus") == 200 and "MYMEMORY WARNING" not in out.upper():
            return out
        print(f"[AVISO] tradução MyMemory: {j.get('responseStatus')} {str(j.get('responseDetails'))[:120]}")
    except Exception as e:
        print(f"[AVISO] tradução: {e}")
    return None


def fetch_bond_news(session, old):
    """Notícias dos emissores de bonds (pt e en), juntas com o histórico já salvo; mais recentes primeiro."""
    found = {i["id"]: i for i in old}
    for c in BOND_ISSUERS:
        for lang in ("pt", "en"):
            try:
                items = fetch_news(session, c, lang, "7d")
            except Exception as e:
                print(f"[AVISO] notícias de bond {c['name']} ({lang}): {e}")
                continue
            for n in items:
                if not re.search(c["match"], n["title"], re.I) or BOND_NOISE.search(n["title"]):
                    continue
                key = hashlib.sha1(norm(re.sub(r"\W+", " ", n["title"]))[:90].encode()).hexdigest()[:12]
                if key in found:
                    continue
                cat, score, cats = classify(n["title"])
                found[key] = {"id": key, "company": c["name"], "bond": c["bond"], "title": n["title"], "source": n["source"],
                              "link": n["link"], "published": n["published"].isoformat(timespec="seconds"), "lang": lang,
                              "category": cat, "categories": cats, "score": score,
                              "importance": "alta" if score >= 4 else "média", "tone": tone_of(n["title"])}
    found = {k: i for k, i in found.items() if not BOND_NOISE.search(i.get("titleOrig") or i["title"])}
    items = sorted(dedupe(list(found.values())), key=lambda i: i["published"], reverse=True)[:BOND_KEEP]
    # manchetes em inglês: traduz para o português e guarda o original
    n_tr = 0
    for i in items:
        if i.get("lang") == "en" and not i.get("titleOrig"):
            pt = translate_pt(session, i["title"])
            if pt:
                i["titleOrig"], i["title"] = i["title"], pt
                n_tr += 1
    print(f"[INFO] notícias de bonds: {n_tr} manchetes traduzidas")
    return items


# categorias de notícia material: (rótulo, peso, padrões no título sem acento)
CATEGORIES = [
    ("Fato relevante", 5, [r"fato relevante", r"comunicado ao mercado"]),
    ("Resultado", 4, [r"\blucro", r"prejuizo", r"balanco", r"resultado", r"\b[1-4]t\d{2}\b", r"trimestre",
                      r"\bebitda", r"receita liquida", r"guidance", r"projec"]),
    ("M&A / societário", 5, [r"aquisi", r"adquir", r"compra (da|do|de)", r"fus[aã]o", r"incorpora", r"\bopa\b",
                             r"venda (da|do|de) (participa|controle|unidade|operac)", r"cis[aã]o", r"joint venture",
                             r"controlador", r"reorganiza"]),
    ("Dívida / rating", 4, [r"debenture", r"emiss[aã]o", r"follow.?on", r"oferta de a", r"capta", r"\bdivida",
                            r"alavancagem", r"\brating", r"fitch", r"moody", r"s&p", r"standard & poor", r"refinanci",
                            r"recuperac[aã]o judicial", r"covenant", r"bonds?\b", r"notes\b"]),
    ("Proventos / recompra", 3, [r"dividend", r"\bjcp\b", r"juros sobre capital", r"recompra", r"proventos",
                                 r"bonifica", r"desdobramento", r"grupamento"]),
    ("Gestão", 3, [r"\bceo\b", r"presidente", r"renuncia", r"\bcfo\b", r"diretor(a)? financeir", r"conselho de admin",
                   r"sucess[aã]o", r"deixa o cargo", r"assume (a|o) (presid|comando|cargo)"]),
    ("Regulatório / jurídico", 4, [r"\bcade\b", r"\bcvm\b", r"investiga", r"\bprocesso\b", r"\bmulta\b", r"\btcu\b",
                                   r"justica", r"liminar", r"\bstf\b", r"\bstj\b", r"receita federal", r"autua"]),
    ("Analistas", 2, [r"recomenda", r"preco.?alvo", r"rebaix", r"\beleva\b", r"inicia cobertura", r"\bcompra\b.*\b(btg|xp|itau|bradesco|safra|goldman|jpmorgan|morgan|ubs|citi|santander|bofa)\b",
                      r"\b(btg|xp|itau bba|bradesco bbi|safra|goldman|jpmorgan|morgan stanley|ubs|citi|santander|bofa)\b"]),
    ("Operacional", 2, [r"contrato", r"frota", r"concess[aã]o", r"licita", r"investimento de", r"expans[aã]o",
                        r"nova fabrica", r"demiss", r"greve", r"recall", r"parceria"]),
    ("Mercado", 1, [r"dispara", r"despenca", r"desaba", r"salta", r"derrete", r"maior alta", r"maior queda",
                    r"sobem \d", r"caem \d", r"sobe \d", r"cai \d"]),
]

# ruído: listas genéricas, conteúdo patrocinado, dicas de investimento
NOISE = [r"acoes para (comprar|investir)", r"carteira recomendada", r"vale a pena", r"como investir",
         r"\bveja (as|os) \d+", r"\btop \d+", r"quiz", r"horoscopo", r"patrocinado", r"\bcursos?\b",
         r"agenda de dividendos da semana", r"^ibovespa hoje", r"o que (esperar|abre|fecha)",
         r"vagas de emprego", r"estagio"]

POSITIVE = [r"(corta|reduz|diminui) (a )?divida", r"desalavanc", r"\bsobe", r"\balta de", r"cresce", r"dispara", r"salta", r"lucro (cresce|sobe|avanca|dispara|recorde)", r"supera", r"\beleva\b",
            r"aprova", r"recompra", r"dividend", r"\bjcp\b", r"melhora", r"recorde", r"upgrade", r"compra\b"]
NEGATIVE = [r"\bcai\b", r"\bcaem\b", r"despenca", r"desaba", r"derrete", r"prejuizo", r"rebaix", r"\bcorta (?!(a )?divida)",
            r"investiga", r"\bmulta", r"renuncia", r"recuperac[aã]o judicial", r"piora", r"frustra", r"abaixo",
            r"downgrade", r"queda(?! d(os|a) (juros|selic))", r"venda\b.*\b(btg|xp|itau|goldman|jpmorgan|ubs)\b"]

MARKET = [("^BVSP", "Ibovespa", 0), ("BRL=X", "Dólar (R$)", 4)]


def norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def mentions(company, title):
    """O título cita a empresa (nome com maiúscula ou ticker) e não é homônimo."""
    if not re.search(company["match"], title):
        return False
    return not (company.get("exclude") and re.search(company["exclude"], title))


def is_material(company, title):
    cat, score, _ = classify(title)
    return mentions(company, title) and bool(cat) and score >= 2


STOPWORDS = {"sobre", "para", "com", "apos", "pela", "pelo", "mais", "veja", "data", "acoes", "milhoes", "bilhoes",
             "anuncia", "confirma", "pagamento", "empresa", "companhia"}


def tokens(title):
    return {w for w in re.findall(r"[a-z0-9]+", norm(title))
            if (len(w) > 3 or (w.isdigit() and len(w) >= 3)) and w not in STOPWORDS}


def same_fact(a, b):
    if a["company"] != b["company"]:
        return False
    ta, tb = tokens(a["title"]), tokens(b["title"])
    if len(ta & tb) / max(1, len(ta | tb)) >= 0.3:
        return True
    # mesma categoria e mesmo valor citado (ex.: "R$ 421 milhões") é o mesmo fato
    nums = {w for w in ta & tb if w.isdigit()}
    return bool(nums) and a["category"] == b["category"]


def dedupe(items):
    """Junta manchetes da mesma empresa sobre o mesmo fato (fontes diferentes, redação parecida)."""
    ranked = sorted(items, key=lambda i: (i["importance"] != "alta", -i["score"], i["published"]))
    kept = []
    for it in ranked:
        dup = next((k for k in kept if same_fact(k, it)), None)
        if dup:
            dup.setdefault("alsoIn", [])
            if it["source"] not in dup["alsoIn"] and it["source"] != dup["source"]:
                dup["alsoIn"].append(it["source"])
            continue
        kept.append(it)
    return kept


def classify(title):
    t = norm(title)
    if any(re.search(p, t) for p in NOISE):
        return None, 0, []
    cats, score = [], 0
    for label, weight, pats in CATEGORIES:
        if any(re.search(p, t) for p in pats):
            cats.append(label)
            score += weight
    return (cats[0] if cats else None), score, cats


def tone_of(title):
    t = norm(title)
    pos = sum(bool(re.search(p, t)) for p in POSITIVE)
    neg = sum(bool(re.search(p, t)) for p in NEGATIVE)
    return "positivo" if pos > neg else "negativo" if neg > pos else "neutro"


def fetch_news(session, company, lang="pt", window="2d"):
    loc = "&hl=pt-BR&gl=BR&ceid=BR:pt-419" if lang == "pt" else "&hl=en-US&gl=US&ceid=US:en"
    url = "https://news.google.com/rss/search?q=" + quote_plus(company["query"] + f" when:{window}") + loc
    r = session.get(url, timeout=20)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    out = []
    for it in root.iter("item"):
        raw_title = (it.findtext("title") or "").strip()
        source = (it.findtext("source") or "").strip()
        # Google News anexa " - Fonte" no fim do título
        title = raw_title[: -len(source) - 3] if source and raw_title.endswith(" - " + source) else raw_title
        try:
            pub = parsedate_to_datetime(it.findtext("pubDate"))
        except Exception:
            continue
        out.append({"title": html.unescape(title), "source": source, "link": it.findtext("link") or "",
                    "published": pub.astimezone(timezone.utc)})
    return out


# documentos entregues à CVM (RAD): fato relevante, comunicado ao mercado e aviso aos acionistas.
# Saem muitas vezes à noite e nem sempre viram notícia no Google News.
CVM_URL = "https://www.rad.cvm.gov.br/ENET/frmConsultaExternaCVM.aspx"
CVM_KEEP = ("Fato Relevante", "Comunicado ao Mercado", "Aviso aos Acionistas")


def fetch_cvm_filings(session, days=3):
    hoje = datetime.now(BRT)
    body = {"dataDe": (hoje - timedelta(days=days)).strftime("%d/%m/%Y"), "dataAte": hoje.strftime("%d/%m/%Y"),
            "empresa": "", "setorAtividade": "-1", "categoriaEmissor": "-1", "situacaoEmissor": "-1",
            "tipoParticipante": "-1", "dataReferencia": "", "categoria": "IPE_-1_-1_-1", "periodo": "2",
            "horaIni": "", "horaFim": "", "palavraChave": "", "ultimaDtRef": "false", "tipoEmpresa": "0",
            "token": "", "versaoCaptcha": ""}
    session.get(CVM_URL, timeout=30)
    r = session.post(CVM_URL + "/ListarDocumentos", data=json.dumps(body), timeout=60,
                     headers={"Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest",
                              "Referer": CVM_URL})
    r.raise_for_status()
    d = r.json()["d"]
    if d.get("temErro"):
        raise RuntimeError(d.get("msgErro"))
    out = []
    for row in (d.get("dados") or "").split("&*"):
        f = row.split("$&")
        if len(f) < 11:
            continue
        clean = [re.sub(r"<spanOrder>.*?</spanOrder>|<[^>]+>", "", x).strip() for x in f]
        name, categoria, tipo, especie, entrega = clean[1], clean[2], clean[3], clean[4], clean[6]
        if categoria not in CVM_KEEP:
            continue
        company = next((c for c in COMPANIES if c.get("cvm") and re.search(c["cvm"], norm(name).upper())), None)
        if not company:
            continue
        prot = re.search(r"NumeroProtocoloEntrega=(\d+)", f[10])
        try:
            pub = datetime.strptime(entrega, "%d/%m/%Y %H:%M").replace(tzinfo=BRT)
        except ValueError:
            continue
        detalhe = especie if especie and especie != "-" else (tipo if tipo and tipo != "-" else "")
        title = f"{company['name']} · {categoria}" + (f": {detalhe}" if detalhe else "")
        out.append({"company": company, "title": title, "categoria": categoria, "published": pub.astimezone(timezone.utc),
                    "link": f"https://www.rad.cvm.gov.br/ENET/frmExibirArquivoIPEExterno.aspx?NumeroProtocoloEntrega={prot.group(1)}"
                            if prot else CVM_URL})
    return out


def market_snapshot(session, tickers):
    rows = []
    for sym, label, casas in MARKET + [(t + ".SA", t, 2) for t in tickers]:
        try:
            meta = fetch_chart_meta(session, sym)
            price, prev = meta.get("regularMarketPrice"), meta.get("previousClose") or meta.get("chartPreviousClose")
            rows.append({"symbol": label, "price": price, "pct": (price - prev) / prev * 100 if price and prev else None,
                         "decimals": casas})
        except Exception as e:
            print(f"[AVISO] {sym}: {e}")
    return rows


def fetch_chart_meta(session, sym):
    last = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            r = session.get(f"https://{host}/v8/finance/chart/{quote_plus(sym)}",
                            params={"range": "1d", "interval": "1d"}, timeout=15)
            r.raise_for_status()
            return r.json()["chart"]["result"][0]["meta"]
        except Exception as e:
            last = e
    raise RuntimeError(last)


# ---------------------------------------------------------------- e-mail
def off_hours(item):
    """Saiu fora do horário comercial (19h às 8h de Brasília, ou no fim de semana)."""
    t = datetime.fromisoformat(item["published"]).astimezone(BRT)
    return t.weekday() >= 5 or t.hour >= 19 or t.hour < 8


def build_email(edition, now, new_items, market):
    hora = now.strftime("%d/%m/%Y")
    alta = [i for i in new_items if i["importance"] == "alta"]
    subject = (f"[Notícias B3] {edition.capitalize()} {now.strftime('%d/%m')} · "
               + (f"{len(new_items)} notícias materiais" if new_items else "sem notícias materiais novas")
               + (f" ({len(alta)} de alta relevância)" if alta else ""))

    from email_layout import UP, DOWN, INK, MUTED, FONT, data_table, section_title, row, button, page, esc, color_for
    noite = sum(1 for i in new_items if off_hours(i))
    if noite and edition == "manhã":
        subject += f" · {noite} saíram à noite"
    arrow = {"positivo": ("▲", UP), "negativo": ("▼", DOWN), "neutro": ("■", MUTED)}

    mk = [m for m in market if m["pct"] is not None]
    mrows = [[f"<b>{esc(m['symbol'])}</b>",
              f"<b>{br(m['price'], m['decimals']) if m['decimals'] else br(m['price'], 0)}</b>",
              f'<b style="color:{color_for(m["pct"])}">{"+" if m["pct"] >= 0 else "−"}{br(abs(m["pct"]))}%</b>'] for m in mk]
    # duas colunas lado a lado para caber em pouco espaço
    half = (len(mrows) + 1) // 2
    left, right = mrows[:half], mrows[half:] + [["", "", ""]] * (half - len(mrows[half:]))
    market_tbl = data_table(["Ativo", "Último", "Dia", "Ativo", "Último", "Dia"],
                            [l + r for l, r in zip(left, right)], ["left", "right", "right", "left", "right", "right"])

    items_html = ""
    for i in new_items:
        sym, col = arrow[i["tone"]]
        when = datetime.fromisoformat(i["published"]).astimezone(BRT).strftime("%d/%m %H:%M")
        tag_bg = "#fde68a" if i["importance"] == "alta" else "#e5e7eb"
        extra = f" · também em {len(i['alsoIn'])} outra(s) fonte(s)" if i.get("alsoIn") else ""
        night = (f'<span style="background:#1e3a5f;color:#ffffff;padding:1px 6px;font-weight:700">à noite</span> '
                 if off_hours(i) else "")
        items_html += row(
            f'<div style="font:12px {FONT};color:{MUTED}"><b style="color:#1d4ed8">{esc(" · ".join(i["tickers"]))}</b> · {esc(i["company"])} · {when} '
            + night + (f'<span style="background:{tag_bg};color:{INK};padding:1px 6px;font-weight:700">{esc(i["category"])}</span> ' if i.get("category") else "") +
            f'<b style="color:{col}">{sym} {esc(i["tone"])}</b></div>'
            f'<div style="margin-top:4px"><a href="{esc(i["link"])}" style="font:600 15px {FONT};color:{INK};text-decoration:none">{esc(i["title"])}</a></div>'
            f'<div style="font:12px {FONT};color:{MUTED};margin-top:2px">{esc(i["source"])}{extra}</div>')
    if not new_items:
        items_html = row(f'<span style="color:{MUTED}">Nenhuma notícia material nova desde o último boletim. O painel mostra as anteriores.</span>')

    html_body = page("BOLETIM B3 · MOBILIDADE E LOGÍSTICA", f"Edição da {edition} · {hora}", "Mercado e notícias materiais desde o último boletim" + (" (inclui o que saiu à noite)" if edition == "manhã" else ""),
                     section_title("Mercado") + market_tbl + section_title("Notícias materiais") + items_html
                     + button(DASHBOARD_URL, "Abrir painel com gráficos e notícias"),
                     "Fatos relevantes, comunicados ao mercado e avisos aos acionistas entregues à CVM entram sempre. "
                     "Seleção automática de notícias do Google News que mencionam as empresas e tratam de resultado, M&amp;A, dívida e rating, "
                     "proventos, gestão, regulatório, analistas ou contratos relevantes. O sinal ▲/▼ é uma leitura automática do título, não uma "
                     "recomendação. Cotações do Yahoo Finance com atraso de até 15 min.")

    lines = [f"Boletim B3 · edição da {edition} · {hora}", ""]
    lines += [f"{m['symbol']}: {'+' if m['pct'] >= 0 else '−'}{br(abs(m['pct']))}%" for m in market if m["pct"] is not None]
    lines.append("")
    for i in new_items or []:
        lines.append(f"{'[à noite] ' if off_hours(i) else ''}[{'/'.join(i['tickers'])}] {i['category']} ({i['tone']}): {i['title']} — {i['source']}\n  {i['link']}")
    if not new_items:
        lines.append("Nenhuma notícia material nova desde o último boletim.")
    lines += ["", f"Painel: {DASHBOARD_URL}"]
    return subject, "\n".join(lines), html_body


def build_bond_email(edition, now, new_items):
    """E-mail das notícias dos bonds em US$ (só emissores sem ação na B3), com preço e YTM do monitor Bloomberg."""
    hora = now.strftime("%d/%m/%Y")
    alta = [i for i in new_items if i["importance"] == "alta"]
    subject = (f"[Notícias Bonds] {edition.capitalize()} {now.strftime('%d/%m')} · "
               + (f"{len(new_items)} notícias" if new_items else "sem notícias novas")
               + (f" ({len(alta)} de alta relevância)" if alta else ""))
    from email_layout import UP, DOWN, INK, MUTED, FONT, data_table, section_title, row, button, page, esc, color_for
    arrow = {"positivo": ("▲", UP), "negativo": ("▼", DOWN), "neutro": ("■", MUTED)}

    mon, upd = [], ""
    try:
        bd = json.loads(BONDS_FILE.read_text())
        upd = bd.get("updatedLabel") or ""
        mon = [b for b in bd.get("bonds", []) if not any(b["issuer"].startswith(n) for n in BOND_LISTED)]
    except (OSError, json.JSONDecodeError):
        pass
    def bps(v):
        return "—" if v is None else f'<b style="color:{color_for(v, invert=True)}">{"+" if v > 0 else ""}{round(v)}</b>'
    mon_html = ""
    if mon:
        mon_html = section_title(f"Monitor Bloomberg · {upd}" if upd else "Monitor Bloomberg") + data_table(
            ["Emissor", "Bond", "Preço", "YTM", "Δ 1D (bps)", "Δ 1S (bps)"],
            [[f"<b>{esc(b['issuer'])}</b>", esc(b.get("bond")), br(b.get("px")) if b.get("px") is not None else "—",
              (br(b["ytm"]) + "%") if b.get("ytm") is not None else "—", bps(b.get("d1")), bps(b.get("d1w"))] for b in mon])

    items_html = ""
    for i in new_items:
        sym, col = arrow[i["tone"]]
        when = datetime.fromisoformat(i["published"]).astimezone(BRT).strftime("%d/%m %H:%M")
        tag_bg = "#fde68a" if i["importance"] == "alta" else "#e5e7eb"
        orig = (f'<div style="font:12px {FONT};color:{MUTED};margin-top:2px">Original: {esc(i["titleOrig"])}</div>'
                if i.get("titleOrig") else "")
        items_html += row(
            f'<div style="font:12px {FONT};color:{MUTED}"><b style="color:#1d4ed8">{esc(i["company"])}</b> · {esc(i.get("bond") or "")} · {when} '
            + (f'<span style="background:{tag_bg};color:{INK};padding:1px 6px;font-weight:700">{esc(i["category"])}</span> ' if i.get("category") else "") +
            f'<b style="color:{col}">{sym} {esc(i["tone"])}</b></div>'
            f'<div style="margin-top:4px"><a href="{esc(i["link"])}" style="font:600 15px {FONT};color:{INK};text-decoration:none">{esc(i["title"])}</a></div>'
            f'{orig}<div style="font:12px {FONT};color:{MUTED};margin-top:2px">{esc(i["source"])}</div>')
    if not new_items:
        items_html = row(f'<span style="color:{MUTED}">Nenhuma notícia nova dos emissores desde o último boletim. A aba Bond do painel mostra as anteriores.</span>')

    issuers = ", ".join(c["name"] for c in BOND_ISSUERS if c["name"] not in BOND_LISTED)
    html_body = page("BOLETIM DE BONDS · US$", f"Edição da {edition} · {hora}", f"Notícias de {issuers}",
                     mon_html + section_title("Notícias") + items_html + button(DASHBOARD_URL, "Abrir a aba Bond do painel"),
                     "Notícias do Google News (português e inglês, manchetes em inglês traduzidas) sobre dívida, rating, resultado e "
                     "eventos de crédito dos emissores. Movida, Simpar, Vamos e Tupy têm ação na B3 e entram no boletim das ações. "
                     "Preços e YTM da planilha Monitor_Bonds_Resumido_BDP (Bloomberg). O sinal ▲/▼ é uma leitura automática do título.")
    lines = [f"Boletim de bonds · edição da {edition} · {hora}", ""]
    lines += [f"{b['issuer']} {b.get('bond')}: YTM {br(b['ytm'])}%" for b in mon if b.get("ytm") is not None]
    lines.append("")
    for i in new_items:
        lines.append(f"[{i['company']}] {i['category']} ({i['tone']}): {i['title']} — {i['source']}\n  {i['link']}")
    if not new_items:
        lines.append("Nenhuma notícia nova dos emissores desde o último boletim.")
    lines += ["", f"Painel: {DASHBOARD_URL}"]
    return subject, "\n".join(lines), html_body


# ---------------------------------------------------------------- principal
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-email", action="store_true", help="só atualiza alerts/news.json (para o painel)")
    args = ap.parse_args()

    now = datetime.now(BRT)
    edition = "manhã" if now.hour < 13 else "noite"
    OUT_DIR.mkdir(exist_ok=True)

    state = {"seen": {}, "lastRun": None}
    if STATE_FILE.exists():
        try:
            state.update(json.loads(STATE_FILE.read_text()))
        except json.JSONDecodeError:
            pass
    cutoff_seen = (datetime.now(timezone.utc) - timedelta(days=SEEN_DAYS)).isoformat()
    state["seen"] = {k: v for k, v in state["seen"].items() if v >= cutoff_seen}
    since = (datetime.fromisoformat(state["lastRun"]) if state.get("lastRun")
             else datetime.now(timezone.utc) - timedelta(hours=24))
    since = max(since - timedelta(hours=1), datetime.now(timezone.utc) - timedelta(hours=36))

    session = requests.Session()
    session.headers.update(HEADERS)

    found, errors = {}, 0
    for c in COMPANIES:
        try:
            items = fetch_news(session, c)
        except Exception as e:
            errors += 1
            print(f"[ERRO] notícias {c['name']}: {e}")
            continue
        for n in items:
            if not is_material(c, n["title"]):
                continue
            cat, score, cats = classify(n["title"])
            key = hashlib.sha1(norm(re.sub(r"\W+", " ", n["title"]))[:90].encode()).hexdigest()[:12]
            if key in found:  # mesma manchete em outra empresa ou fonte
                found[key]["tickers"] = sorted(set(found[key]["tickers"]) | set(c["tickers"]))
                continue
            found[key] = {
                "id": key, "tickers": list(c["tickers"]), "company": c["name"], "title": n["title"],
                "source": n["source"], "link": n["link"], "published": n["published"].isoformat(timespec="seconds"),
                "category": cat, "categories": cats, "score": score,
                "importance": "alta" if score >= 4 else "média", "tone": tone_of(n["title"]),
            }
    if errors == len(COMPANIES):
        print("[ERRO] Nenhuma busca de notícias funcionou.")
        sys.exit(1)

    found = {i["id"]: i for i in dedupe(list(found.values()))}
    try:
        filings = fetch_cvm_filings(session)
        print(f"[INFO] CVM: {len(filings)} documentos das empresas")
    except Exception as e:
        filings = []
        print(f"[AVISO] CVM: {e}")
    for d in filings:
        c = d["company"]
        cat, score, cats = classify(d["title"])
        if d["categoria"] != "Aviso aos Acionistas" or not cat:
            cat, score = "Fato relevante", max(score, 5)
            cats = [cat] + [x for x in cats if x != cat]
        key = "cvm" + hashlib.sha1(d["link"].encode()).hexdigest()[:9]
        found[key] = {
            "id": key, "tickers": list(c["tickers"]), "company": c["name"], "title": d["title"], "source": "CVM",
            "link": d["link"], "published": d["published"].isoformat(timespec="seconds"),
            "category": cat, "categories": cats, "score": score,
            "importance": "alta" if score >= 4 else "média", "tone": tone_of(d["title"]),
        }
    # documentos da CVM: janela de 48h (o "seen" evita repetir), para não perder o que saiu à noite
    since_cvm = min(since, datetime.now(timezone.utc) - timedelta(hours=48))
    fresh = [i for i in found.values()
             if datetime.fromisoformat(i["published"]) >= (since_cvm if i["source"] == "CVM" else since)]
    # alta relevância primeiro; dentro de cada grupo, mais recentes primeiro
    new_items = sorted((i for i in fresh if i["id"] not in state["seen"]),
                       key=lambda i: (i["importance"] != "alta", -datetime.fromisoformat(i["published"]).timestamp()))

    tickers = [t for c in COMPANIES for t in c["tickers"]]
    market = market_snapshot(session, tickers)

    # histórico para o painel: junta com o que já havia, mais recentes primeiro
    old, old_bonds = [], []
    if NEWS_FILE.exists():
        try:
            _prev = json.loads(NEWS_FILE.read_text())
            old, old_bonds = _prev.get("items", []), _prev.get("bondItems", [])
        except json.JSONDecodeError:
            old = []
    bond_items = fetch_bond_news(session, old_bonds)
    print(f"[INFO] notícias de bonds: {len(bond_items)} no histórico")
    # revalida o histórico com as regras atuais (remove o que deixou de passar no filtro)
    by_name = {c["name"]: c for c in COMPANIES}
    old = [i for i in old if i.get("company") in by_name
           and (i.get("source") == "CVM" or is_material(by_name[i["company"]], i["title"]))]
    for i in old:
        if i.get("source") == "CVM":
            continue
        cat, score, cats = classify(i["title"])
        i.update(category=cat, categories=cats, score=score, tone=tone_of(i["title"]),
                 importance="alta" if score >= 4 else "média")
    merged = {i["id"]: i for i in old}
    merged.update({i["id"]: i for i in found.values()})
    items = sorted(dedupe(list(merged.values())), key=lambda i: i["published"], reverse=True)[:KEEP_ITEMS]
    NEWS_FILE.write_text(json.dumps({
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "edition": edition, "market": market, "items": items, "bondItems": bond_items,
    }, ensure_ascii=False))

    if args.no_email:
        print(f"[INFO] Painel atualizado com {len(items)} notícias ({len(new_items)} novas desde o último boletim); sem e-mail.")
        return

    # notícias de bond: das empresas com ação na B3 vão para o e-mail das ações; das demais, para o e-mail de bonds
    fresh_b = [i for i in bond_items if datetime.fromisoformat(i["published"]) >= since and i["id"] not in state["seen"]]
    local_extra = [dict(i, tickers=BOND_LISTED[i["company"]]) for i in fresh_b if i["company"] in BOND_LISTED]
    local_extra = [i for i in local_extra if i["id"] not in {x["id"] for x in new_items}
                   and not any(same_fact(i, x) for x in new_items)]
    new_items = sorted(new_items + local_extra,
                       key=lambda i: (i["importance"] != "alta", -datetime.fromisoformat(i["published"]).timestamp()))
    new_bonds = sorted((i for i in fresh_b if i["company"] not in BOND_LISTED),
                       key=lambda i: (i["importance"] != "alta", -datetime.fromisoformat(i["published"]).timestamp()))

    subject, text, html_body = build_email(edition, now, new_items, market)
    b_subject, b_text, b_html = build_bond_email(edition, now, new_bonds)
    print(subject)
    print(text)
    print(b_subject)
    print(b_text)
    if args.dry_run:
        (OUT_DIR / "news_preview.html").write_text(html_body)
        (OUT_DIR / "news_bonds_preview.html").write_text(b_html)
        print("[INFO] Prévias salvas em alerts/news_preview.html e alerts/news_bonds_preview.html (nada enviado).")
        return

    send_email(subject, text, html_body)
    send_email(b_subject, b_text, b_html)
    for i in new_items + new_bonds:
        state["seen"][i["id"]] = i["published"]
    state["lastRun"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    STATE_FILE.write_text(json.dumps(state, indent=1))
    print("[INFO] E-mails enviados (ações e bonds).")


if __name__ == "__main__":
    main()
