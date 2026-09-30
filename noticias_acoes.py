"""
Boletim de notícias materiais das ações B3
------------------------------------------
Roda todo dia às 8h30 e às 18h30 (via GitHub Actions). Busca notícias das
empresas no Google News, mantém só as que podem mexer com a ação (resultado,
M&A, dívida e rating, proventos, gestão, regulatório, recomendação de
analistas, contratos relevantes), monta um resumo do mercado e envia por e-mail.

Também grava alerts/news.json, que alimenta a faixa de notícias do painel
publicado no claude.ai.

E-mail via as mesmas variáveis do monitor:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM, EMAIL_TO

Uso:
  python noticias_acoes.py              # busca, grava e envia
  python noticias_acoes.py --dry-run    # não envia; salva alerts/news_preview.html
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
    {"tickers": ["MOVI3"], "name": "Movida",
     "query": '"Movida" (locadora OR MOVI3 OR ações OR aluguel OR carros) OR MOVI3',
     "match": r"\bMovida\b|MOVI3"},
    {"tickers": ["SIMH3"], "name": "Simpar",
     "query": "Simpar OR SIMH3", "match": r"\bSimpar\b|\bSIMPAR\b|SIMH3"},
    {"tickers": ["VAMO3"], "name": "Vamos",
     "query": '"Grupo Vamos" OR "Vamos Locação" OR VAMO3',
     "match": r"Grupo Vamos|Vamos Loca|VAMO3"},
    {"tickers": ["JSLG3"], "name": "JSL",
     "query": 'JSLG3 OR "JSL" logística OR "JSL S.A."', "match": r"\bJSL\b|JSLG3"},
    {"tickers": ["AMOB3"], "name": "Automob",
     "query": "Automob OR AMOB3", "match": r"\bAutomob\b|AMOB3"},
    {"tickers": ["RAPT3", "RAPT4"], "name": "Randoncorp",
     "query": "Randoncorp OR Randon OR RAPT4 OR RAPT3", "match": r"\bRandon(corp)?\b|RAPT[34]"},
    {"tickers": ["RENT3"], "name": "Localiza",
     "query": "Localiza OR RENT3", "match": r"\bLocaliza\b|RENT3"},
    {"tickers": ["FRAS3"], "name": "Frasle Mobility",
     "query": 'Frasle OR "Fras-le" OR FRAS3', "match": r"\bFras-?le\b|\bFrasle\b|FRAS3"},
    {"tickers": ["ARML3"], "name": "Armac",
     "query": "Armac OR ARML3", "match": r"\bArmac\b|ARML3"},
    {"tickers": ["MILS3"], "name": "Mills",
     "query": 'MILS3 OR "Mills Locação" OR "Mills Estruturas" OR "Mills (MILS3)"',
     "match": r"\bMills\b|MILS3", "exclude": r"General Mills"},
    {"tickers": ["PRNR3"], "name": "Priner",
     "query": "Priner OR PRNR3", "match": r"\bPriner\b|PRNR3"},
]

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


def fetch_news(session, company):
    url = ("https://news.google.com/rss/search?q=" + quote_plus(company["query"] + " when:2d")
           + "&hl=pt-BR&gl=BR&ceid=BR:pt-419")
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
def build_email(edition, now, new_items, market):
    hora = now.strftime("%d/%m/%Y")
    alta = [i for i in new_items if i["importance"] == "alta"]
    subject = (f"[Notícias B3] {edition.capitalize()} {now.strftime('%d/%m')} · "
               + (f"{len(new_items)} notícias materiais" if new_items else "sem notícias materiais novas")
               + (f" ({len(alta)} de alta relevância)" if alta else ""))

    tone_color = {"positivo": "#137333", "negativo": "#c5221f", "neutro": "#5d6570"}
    tone_arrow = {"positivo": "▲", "negativo": "▼", "neutro": "■"}

    def mk_row(m):
        if m["pct"] is None:
            return ""
        up = m["pct"] >= 0
        return (f'<td style="padding:6px 10px;white-space:nowrap;border-bottom:1px solid #2a2f36">'
                f'<span style="color:#f5a623;font-weight:700">{m["symbol"]}</span> '
                f'<span style="color:#e8eaed">{br(m["price"], m["decimals"]) if m["decimals"] else br(m["price"], 0)}</span> '
                f'<span style="color:{"#5fd38d" if up else "#ff6b6b"}">{"+" if up else "−"}{br(abs(m["pct"]))}%</span></td>')

    cells = [mk_row(m) for m in market if m["pct"] is not None]
    grid = "".join("<tr>" + "".join(cells[i:i + 3]) + "</tr>" for i in range(0, len(cells), 3))

    def item_html(i):
        tag_bg = "#fdf1d8" if i["importance"] == "alta" else "#eef1f5"
        tag_fg = "#8a5a00" if i["importance"] == "alta" else "#5d6570"
        when = datetime.fromisoformat(i["published"]).astimezone(BRT).strftime("%d/%m %H:%M")
        return f"""
      <tr><td style="padding:12px 16px;border-bottom:1px solid #e2e6eb">
        <div style="font-size:12px;margin-bottom:3px">
          <b style="color:#1a5fd1">{' · '.join(i['tickers'])}</b>
          <span style="color:#5d6570"> · {i['company']} · {when}</span>
          <span style="margin-left:6px;padding:1px 6px;border-radius:5px;background:{tag_bg};color:{tag_fg};font-weight:700;font-size:11px">{i['category']}</span>
          <span style="margin-left:4px;color:{tone_color[i['tone']]};font-size:11px;font-weight:700">{tone_arrow[i['tone']]} {i['tone']}</span>
        </div>
        <a href="{html.escape(i['link'])}" style="color:#1f2328;text-decoration:none;font-size:15px;line-height:1.35">{html.escape(i['title'])}</a>
        <div style="font-size:12px;color:#5d6570;margin-top:2px">{html.escape(i['source'])}{f" · também em {len(i['alsoIn'])} outra(s) fonte(s)" if i.get('alsoIn') else ""}</div>
      </td></tr>"""

    body_items = "".join(item_html(i) for i in new_items) if new_items else (
        '<tr><td style="padding:18px 16px;color:#5d6570">Nenhuma notícia material nova desde o último boletim. '
        'O painel mostra as notícias anteriores.</td></tr>')

    html_body = f"""<!doctype html><html><body style="margin:0;background:#f5f7fa;font-family:Roboto,Arial,sans-serif;color:#1f2328">
  <div style="max-width:680px;margin:0 auto;padding:20px 12px">
    <div style="background:#0f1216;border-radius:12px 12px 0 0;padding:16px 18px">
      <div style="color:#f5a623;font-size:12px;font-weight:700;letter-spacing:.08em">BOLETIM B3 · MOBILIDADE E LOGÍSTICA</div>
      <div style="color:#ffffff;font-size:20px;margin-top:4px">Edição da {edition} · {hora}</div>
      <table style="border-collapse:collapse;margin-top:10px;font-size:13px;font-family:'Roboto Mono',Consolas,monospace">{grid}</table>
    </div>
    <div style="background:#ffffff;border:1px solid #e2e6eb;border-top:0;border-radius:0 0 12px 12px;overflow:hidden">
      <div style="padding:12px 16px;font-size:12px;color:#5d6570;border-bottom:1px solid #e2e6eb;text-transform:uppercase;letter-spacing:.06em">
        Notícias materiais {'desde o último boletim' if new_items else ''}</div>
      <table style="width:100%;border-collapse:collapse">{body_items}</table>
      <div style="padding:14px 16px"><a href="{DASHBOARD_URL}" style="display:inline-block;padding:8px 16px;border-radius:8px;
        background:#1a5fd1;color:#ffffff;text-decoration:none;font-size:13px;font-weight:500">Abrir painel com gráficos e notícias</a></div>
    </div>
    <p style="font-size:11px;color:#5d6570;line-height:1.5;margin:12px 4px 0">
      Seleção automática de notícias do Google News que mencionam as empresas e tratam de resultado, M&amp;A, dívida e rating,
      proventos, gestão, regulatório, recomendações de analistas ou contratos relevantes. O sinal ▲/▼ é uma leitura automática
      do título, não uma recomendação. Cotações do Yahoo Finance com atraso de até 15 min.
    </p>
  </div>
</body></html>"""

    lines = [f"Boletim B3 · edição da {edition} · {hora}", ""]
    lines += [f"{m['symbol']}: {'+' if m['pct'] >= 0 else '−'}{br(abs(m['pct']))}%" for m in market if m["pct"] is not None]
    lines.append("")
    for i in new_items or []:
        lines.append(f"[{'/'.join(i['tickers'])}] {i['category']} ({i['tone']}): {i['title']} — {i['source']}\n  {i['link']}")
    if not new_items:
        lines.append("Nenhuma notícia material nova desde o último boletim.")
    lines += ["", f"Painel: {DASHBOARD_URL}"]
    return subject, "\n".join(lines), html_body


# ---------------------------------------------------------------- principal
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
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
    fresh = [i for i in found.values() if datetime.fromisoformat(i["published"]) >= since]
    # alta relevância primeiro; dentro de cada grupo, mais recentes primeiro
    new_items = sorted((i for i in fresh if i["id"] not in state["seen"]),
                       key=lambda i: (i["importance"] != "alta", -datetime.fromisoformat(i["published"]).timestamp()))

    tickers = [t for c in COMPANIES for t in c["tickers"]]
    market = market_snapshot(session, tickers)

    # histórico para o painel: junta com o que já havia, mais recentes primeiro
    old = []
    if NEWS_FILE.exists():
        try:
            old = json.loads(NEWS_FILE.read_text()).get("items", [])
        except json.JSONDecodeError:
            old = []
    # revalida o histórico com as regras atuais (remove o que deixou de passar no filtro)
    by_name = {c["name"]: c for c in COMPANIES}
    old = [i for i in old if i.get("company") in by_name and is_material(by_name[i["company"]], i["title"])]
    for i in old:
        cat, score, cats = classify(i["title"])
        i.update(category=cat, categories=cats, score=score, tone=tone_of(i["title"]),
                 importance="alta" if score >= 4 else "média")
    merged = {i["id"]: i for i in old}
    merged.update({i["id"]: i for i in found.values()})
    items = sorted(dedupe(list(merged.values())), key=lambda i: i["published"], reverse=True)[:KEEP_ITEMS]
    NEWS_FILE.write_text(json.dumps({
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "edition": edition, "market": market, "items": items,
    }, ensure_ascii=False))

    subject, text, html_body = build_email(edition, now, new_items, market)
    print(subject)
    print(text)
    if args.dry_run:
        (OUT_DIR / "news_preview.html").write_text(html_body)
        print("[INFO] Prévia salva em alerts/news_preview.html (nada enviado).")
        return

    send_email(subject, text, html_body)
    for i in new_items:
        state["seen"][i["id"]] = i["published"]
    state["lastRun"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    STATE_FILE.write_text(json.dumps(state, indent=1))
    print("[INFO] E-mail enviado.")


if __name__ == "__main__":
    main()
