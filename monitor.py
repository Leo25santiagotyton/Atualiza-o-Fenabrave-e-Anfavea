"""
Monitor ANFAVEA / FENABRAVE
----------------------------
Verifica periodicamente as páginas de divulgação de dados da ANFAVEA e da
FENABRAVE. Quando detecta um item novo (novo PDF da Carta ANFAVEA, ou nova
notícia/release na página de Imprensa da FENABRAVE), envia um e-mail de
aviso e salva o novo estado em state.json para não avisar de novo o mesmo
item no próximo run.
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MonitorANFAVEAFenabrave/1.0)"
}

SOURCES = [
    {
        "name": "ANFAVEA - Edições em PDF (Carta da Anfavea)",
        "url": "https://anfavea.com.br/site/edicoes-em-pdf/",
        "link_filter": lambda href: href and href.lower().endswith(".pdf"),
    },
    {
        "name": "FENABRAVE - Imprensa (releases mensais)",
        "url": "https://www.fenabrave.org.br/portalv2/home/imprensa",
        "link_filter": lambda href: href and "/Noticia/" in href,
    },
]

MAX_ITEMS_TRACKED = 5


def fetch_links(url: str, link_filter):
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    seen_hrefs = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not link_filter(href):
            continue
        if href.startswith("/"):
            base = "/".join(url.split("/")[:3])
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
            items = fetch_links(source["url"], source["link_filter"])
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
                subject="[Monitor] Atualização ANFAVEA/FENABRAVE detectada",
                body=body,
            )
            print("[INFO] E-mail enviado com sucesso.")
        except Exception as exc:
            print(f"[ERRO] Falha ao enviar e-mail: {exc}", file=sys.stderr)
            sys.exit(1)

    save_state(state)


if __name__ == "__main__":
    main()
