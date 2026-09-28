"""
Monitor de notícias - OHI Group (Omni Helicopters International)
-----------------------------------------------------------------
Busca notícias novas sobre o OHI Group e suas empresas (Omni Táxi Aéreo,
Omni Helicopters International) no Google Notícias (RSS, em português e
inglês). Cada notícia passa por um filtro de relevância para descartar
homônimos comuns (Omni Financeira / Banco Omni, operadora Oi, "omnichannel",
etc.). Quando aparece notícia nova e relevante, envia um e-mail com o título,
o veículo, a data e o link da matéria, e grava o que já foi avisado em
news_state.json para não repetir.

Usa as mesmas variáveis de ambiente de e-mail do monitor.py:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM, EMAIL_TO
"""

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

from monitor import BROWSER_HEADERS, send_email

STATE_FILE = Path(__file__).parent / "news_state.json"

# Buscas no Google Notícias. "when:7d" limita aos últimos 7 dias; o robô
# roda várias vezes por dia, então não perde nada.
QUERIES = [
    '"OHI Group"',
    '"Grupo OHI"',
    '"Omni Helicopters International"',
    '"Omni Helicopters"',
    '"Omni Táxi Aéreo"',
    '"Omni Taxi Aereo"',
    'Omni helicópteros offshore',
    'OHI helicopter offshore',
]
EDITIONS = [
    {"hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"},
    {"hl": "en-US", "gl": "US", "ceid": "US:en"},
    {"hl": "pt-PT", "gl": "PT", "ceid": "PT:pt-150"},
]
QUERY_WINDOW = "7d"

# --- Filtro de relevância (textos comparados sem acento e em minúsculas) ---

# Termos que, sozinhos, já identificam a empresa.
STRONG_TERMS = [
    "ohi group",
    "grupo ohi",
    "omni helicopters international",
    "omni helicopters",
    "omni helicopteros",
    "omni taxi aereo",
    "omni aviacao",
    "omni air taxi",
]

# "Omni" ou "OHI" só contam se aparecerem junto de algum destes termos
# do setor de aviação/offshore.
CONTEXT_TERMS = [
    "helicopter", "helicoptero", "taxi aereo", "aviacao", "aviation",
    "aeronave", "aircraft", "offshore", "oil and gas", "oleo e gas",
    "petroleo", "petrobras", "pre-sal", "aeromedico", "aeromedical",
    "search and rescue", "busca e salvamento", "h175", "h160", "aw139",
    "aw189", "s-92", "sikorsky", "airbus helicopters", "jacarepagua",
    "macae", "anac", "rotorcraft", "air mobility", "mobilidade aerea",
]

# Se aparecer qualquer um destes, a notícia é descartada (homônimos).
EXCLUDE_TERMS = [
    "omni financeira", "banco omni", "omni banco", "grupo omni financeiro",
    "omni credito", "financiamento de veiculos", "credito consignado",
    "omnichannel", "omni-channel", "omnicanal", "omnicom", "omnivision",
    "omni hotels", "omnipod", "omnicell", "omnitracs", "omni logistics",
    "oi s.a", "operadora oi", "oi fibra", "telecom oi",
]

MAX_SEEN = 2000


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower())


def strip_tags(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", text or "")).strip()


def is_relevant(title: str, description: str) -> bool:
    text = normalize(f"{title} {description}")
    if any(term in text for term in EXCLUDE_TERMS):
        return False
    if any(term in text for term in STRONG_TERMS):
        return True
    has_name = re.search(r"\b(omni|ohi)\b", text)
    return bool(has_name) and any(term in text for term in CONTEXT_TERMS)


def build_url(query: str, edition: dict) -> str:
    q = quote_plus(f"{query} when:{QUERY_WINDOW}")
    return (
        f"https://news.google.com/rss/search?q={q}"
        f"&hl={edition['hl']}&gl={edition['gl']}&ceid={edition['ceid']}"
    )


def parse_rss(xml_text: str) -> list:
    root = ET.fromstring(xml_text)
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or link).strip()
        source_el = item.find("source")
        source = source_el.text.strip() if source_el is not None and source_el.text else ""
        pub = item.findtext("pubDate") or ""
        try:
            published = parsedate_to_datetime(pub)
        except Exception:
            published = None
        items.append({
            "id": guid,
            "title": title,
            "link": link,
            "source": source,
            "published": published.isoformat() if published else "",
            "description": strip_tags(item.findtext("description") or ""),
        })
    return items


def fetch_news() -> list:
    found = {}
    for query in QUERIES:
        for edition in EDITIONS:
            url = build_url(query, edition)
            try:
                resp = requests.get(url, headers=BROWSER_HEADERS, timeout=30)
                resp.raise_for_status()
                items = parse_rss(resp.text)
            except Exception as exc:
                print(f"[ERRO] Falha na busca {query} ({edition['hl']}): {exc}", file=sys.stderr)
                continue
            for it in items:
                if it["id"] in found or not is_relevant(it["title"], it["description"]):
                    continue
                found[it["id"]] = it
    return list(found.values())


def dedupe_by_title(items: list) -> list:
    """A mesma matéria costuma aparecer em várias buscas/edições com IDs
    diferentes; aqui fica só uma por título."""
    unique = {}
    for it in items:
        key = normalize(re.sub(r"\s+-\s+[^-]+$", "", it["title"]))
        unique.setdefault(key, it)
    return list(unique.values())


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def format_date(iso: str) -> str:
    if not iso:
        return ""
    dt = datetime.fromisoformat(iso).astimezone(timezone(timedelta(hours=-3)))
    return dt.strftime("%d/%m/%Y %H:%M")


def build_email(items: list) -> tuple:
    plain = [f"{len(items)} nova(s) notícia(s) sobre o OHI Group / Omni Táxi Aéreo:\n"]
    rows = []
    for it in items:
        meta = " · ".join(x for x in (it["source"], format_date(it["published"])) if x)
        plain += [f"- {it['title']}", f"  {meta}", f"  {it['link']}", ""]
        rows.append(
            f'<li style="margin-bottom:14px"><a href="{html.escape(it["link"])}" '
            f'style="font-size:15px;font-weight:bold">{html.escape(it["title"])}</a>'
            f'<br><span style="color:#666;font-size:13px">{html.escape(meta)}</span></li>'
        )
    html_body = (
        '<div style="font-family:Arial,sans-serif">'
        f"<p>{len(items)} nova(s) notícia(s) sobre o <b>OHI Group / Omni Táxi Aéreo</b>:</p>"
        f"<ul>{''.join(rows)}</ul>"
        '<p style="color:#999;font-size:12px">Enviado automaticamente pelo monitor de notícias.</p>'
        "</div>"
    )
    return "\n".join(plain), html_body


def main():
    state = load_state()
    first_run = "seen" not in state
    seen = state.get("seen", [])
    seen_set = set(seen)

    items = fetch_news()
    new_items = [it for it in items if it["id"] not in seen_set]

    if first_run:
        # Na primeira execução avisa só o que saiu nas últimas 48h, para não
        # mandar um e-mail enorme com notícias antigas.
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        to_send = [
            it for it in new_items
            if it["published"] and datetime.fromisoformat(it["published"]) >= cutoff
        ]
    else:
        to_send = new_items

    to_send = dedupe_by_title(to_send)
    to_send.sort(key=lambda it: it["published"], reverse=True)

    print(f"[INFO] {len(items)} notícia(s) relevante(s) encontradas, {len(to_send)} nova(s) para avisar.")

    if to_send:
        plain, html_body = build_email(to_send)
        subject = f"[OHI Group] {len(to_send)} nova(s) notícia(s): {to_send[0]['title'][:90]}"
        try:
            send_email(subject=subject, body=plain, html_body=html_body)
            print("[INFO] E-mail enviado com sucesso.")
        except Exception as exc:
            print(f"[ERRO] Falha ao enviar e-mail: {exc}", file=sys.stderr)
            sys.exit(1)  # não salva o estado, para tentar de novo no próximo run

    for it in new_items:
        seen.append(it["id"])
    state["seen"] = seen[-MAX_SEEN:]
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)


def send_test():
    """Envia um e-mail de teste no formato do monitor, com as notícias
    relevantes dos últimos 7 dias (sem alterar o news_state.json)."""
    items = dedupe_by_title(fetch_news())
    items.sort(key=lambda it: it["published"], reverse=True)
    items = items[:10]
    print(f"[TESTE] {len(items)} notícia(s) relevante(s) nos últimos {QUERY_WINDOW}.")
    if not items:
        items = [{
            "title": "(Exemplo) OHI Group announces leadership transition at Omni Táxi Aéreo",
            "link": "https://verticalmag.com/press-releases/ohi-group-announces-leadership-transition-at-omni-taxi-aereo/",
            "source": "Vertical Mag - nenhuma notícia nova nos últimos 7 dias, este é só um exemplo",
            "published": "",
        }]
    plain, html_body = build_email(items)
    send_email(
        subject="[Teste] Monitor de notícias OHI Group",
        body="E-MAIL DE TESTE\n\n" + plain,
        html_body="<p><b>E-MAIL DE TESTE</b></p>" + html_body,
    )
    print("[TESTE] E-mail de teste enviado com sucesso.")


if __name__ == "__main__":
    if "--teste" in sys.argv:
        send_test()
    else:
        main()
