"""
Monitor ANFAVEA / FENABRAVE / NADA / Auto Innovators
------------------------------------------------------
Verifica periodicamente as páginas de divulgação de dados da ANFAVEA, da
FENABRAVE, da NADA (EUA) e da Alliance for Automotive Innovation (EUA).
Quando detecta um item novo, envia um e-mail de aviso e salva o novo estado
em state.json para não avisar de novo o mesmo item no próximo run.

Configuração de e-mail via variáveis de ambiente (não deixe senha no código):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM, EMAIL_TO
"""

import hashlib
import json
import os
import smtplib
import sys
from email.mime.text import MIMEText
from pathlib import Path

import requests
from bs4 import BeautifulSoup

STATE_FILE = Path(__file__).parent / "state.json"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

SOURCES = [
    {
        "name": "ANFAVEA - Edições em PDF (Carta da Anfavea)",
        "home_url": "https://anfavea.com.br/",
        "url": "https://anfavea.com.br/site/edicoes-em-pdf/",
        "link_filter": lambda href: href and href.lower().endswith(".pdf"),
    },
    {
        "name": "FENABRAVE - Imprensa (releases mensais)",
        "home_url": "https://www.fenabrave.org.br/",
        "url": "https://www.fenabrave.org.br/portalv2/home/imprensa",
        "link_filter": lambda href: href and "/Noticia/" in href,
    },
    {
        "name": "NADA Market Beat (EUA - vendas mensais)",
        "home_url": "https://www.nada.org/",
        "url": "https://www.nada.org/nada/market-beat",
        "link_filter": lambda href: href and "market-beat" in href.lower(),
    },
    {
        "name": "Alliance for Automotive Innovation - Market Reports (EUA)",
        "home_url": "https://www.autosinnovate.org/",
        "url": "https://www.autosinnovate.org/resources/market-reports",
        "link_filter": lambda href: href and ("report" in href.lower() or ".pdf" in href.lower()),
    },
]

MAX_ITEMS_TRACKED = 5


def fetch_links(source):
    """Abre a home primeiro (pra pegar cookies, como um navegador faria) e
    depois busca a página alvo. Retorna lista de (texto, href)."""
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)

    home_url = source.get("home_url")
    if home_url:
        try:
            session.get(home_url, timeout=30)
        except Exception:
            pass  # se a home falhar, tenta direto a página alvo mesmo assim

    headers_with_referer = dict(BROWSER_HEADERS)
    if home_url:
        headers_with_referer["Referer"] = home_url

    resp = session.get(source["url"], headers=headers_with_referer, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    seen_hrefs = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not source["link_filter"](href):
            continue
        if href.startswith("/"):
            base = "/".join(source["url"].split("/")[:3])
            href = base + href
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)
        text = a.get_text(strip=True) or href
        items.append({"text": text, "href": href})
        if len(items) >= MAX_ITEMS_TRACKED:
            break
    return items


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state):
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def hash_items(items):
    raw = json.dumps(items, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def send_email(subject: str, body: str):
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_pass = os.environ["SMTP_PASS"]
    email_from = os.environ.get("EMAIL_FROM", smtp_user)
    email_to = os.environ["EMAIL_TO"]

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = email_from
    msg["To"] = email_to

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(email_from, email_to.split(","), msg.as_string())


def main():
    state = load_state()
    updates_found = []

    for source in SOURCES:
        name = source["name"]
        try:
            items = fetch_links(source)
        except Exception as exc:
            print(f"[ERRO] Falha ao acessar {name}: {exc}", file=sys.stderr)
            continue

        if not items:
            print(f"[AVISO] Nenhum item encontrado em {name} — confira o link_filter/URL.")
            continue

        new_hash = hash_items(items)
        old_hash = state.get(name, {}).get("hash")

        if old_hash is None:
            print(f"[INFO] Primeira execução para {name}. Estado salvo, sem e-mail.")
        elif new_hash != old_hash:
            print(f"[MUDANÇA] Novo conteúdo detectado em {name}.")
            updates_found.append((name, source["url"], items))
        else:
            print(f"[OK] Sem mudanças em {name}.")

        state[name] = {"hash": new_hash, "items": items}

    if updates_found:
        lines = ["Foram detectadas atualizações nas seguintes fontes:\n"]
        for name, url, items in updates_found:
            lines.append(f"### {name}")
            lines.append(f"Página: {url}")
            for it in items[:3]:
                lines.append(f"  - {it['text']} -> {it['href']}")
            lines.append("")
        body = "\n".join(lines)
        try:
            send_email(
                subject="[Monitor] Atualização detectada (ANFAVEA/FENABRAVE/NADA/AutoInnovators)",
                body=body,
            )
            print("[INFO] E-mail enviado com sucesso.")
        except Exception as exc:
            print(f"[ERRO] Falha ao enviar e-mail: {exc}", file=sys.stderr)
            sys.exit(1)

    save_state(state)


if __name__ == "__main__":
    main()
