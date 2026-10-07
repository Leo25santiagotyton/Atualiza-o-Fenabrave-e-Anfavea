"""
Monitor ANFAVEA / FENABRAVE / caminhões nos EUA
-----------------------------------------------
Verifica periodicamente as páginas de divulgação de dados da ANFAVEA e da
FENABRAVE e, nos EUA, só o mercado de caminhões: vendas de caminhões pesados (série
HTRUCKSSAAR do FRED, anualizada) e pedidos de Classe 8 e Classes 5-7 (ACT Research).
Quando detecta um item novo, envia um e-mail de aviso e salva o novo estado
em state.json para não avisar de novo o mesmo item no próximo run.

Configuração de e-mail via variáveis de ambiente (não deixe senha no código):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM, EMAIL_TO
"""

import hashlib
import json
import os
import re
import smtplib
import sys
from email.mime.text import MIMEText
from pathlib import Path

import requests
from bs4 import BeautifulSoup

import monitoramento

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
        "url": "https://anfavea.com.br/site/conteudos/carta-da-anfavea/",
        "link_filter": lambda href: href and "/cartas/" in href.lower() and href.lower().endswith(".pdf"),
    },
    {
        "name": "FENABRAVE - Imprensa (releases mensais)",
        "home_url": "https://www.fenabrave.org.br/",
        "url": "https://www.fenabrave.org.br/portalv2/home/imprensa",
        "link_filter": lambda href: href and "/Noticia/" in href,
    },
    {
        "name": "FRED - vendas de caminhões pesados (EUA)",
        "url": "https://fred.stlouisfed.org/series/HTRUCKSSAAR",
        "fred": "HTRUCKSSAAR",
    },
    {
        "name": "ACT Research - pedidos de caminhões (EUA)",
        "home_url": "https://www.actresearch.net/",
        "url": "https://www.actresearch.net/resources/trends-headlines",
        "link_filter": lambda href: bool(href) and href.startswith("http"),
        # Só pedidos (Classe 8 e Classes 5-7); vendas de usados e fretes ficam de fora.
        "text_filter": lambda t: re.search(r"order", t, re.I) and re.search(r"class|truck", t, re.I),
    },
]

MAX_ITEMS_TRACKED = 5


MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def _pct(a, b):
    if not b:
        return "—"
    return f"{(a / b - 1) * 100:+.1f}%".replace(".", ",")


def fetch_fred(source):
    """Últimas observações de uma série do FRED (CSV público, sem chave).
    Cada item traz o mês, o valor e as variações m/m e a/a."""
    serie = source["fred"]
    resp = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={serie}",
                        headers=BROWSER_HEADERS, timeout=30)
    resp.raise_for_status()
    obs = []
    for linha in resp.text.strip().splitlines()[1:]:
        data, _, valor = linha.partition(",")
        try:
            obs.append((data.strip(), float(valor)))
        except ValueError:
            continue  # "." = sem dado
    items = []
    for i in range(len(obs) - 1, max(len(obs) - 1 - MAX_ITEMS_TRACKED, -1), -1):
        data, v = obs[i]
        ano, mes = int(data[:4]), int(data[5:7])
        mm = _pct(v, obs[i - 1][1]) if i >= 1 else "—"
        aa = _pct(v, obs[i - 12][1]) if i >= 12 else "—"
        mil = v * 1000 if v < 10 else v  # a série vem em milhões de unidades
        num = f"{mil:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
        items.append({"text": f"{MESES[mes - 1]}/{ano} · {num} mil (anualizado) · m/m {mm} · a/a {aa}",
                      "href": f"{source['url']}#{data[:7]}"})
    return items


def fetch_links(source):
    if source.get("fred"):
        return fetch_fred(source)
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
        if source.get("text_filter") and not source["text_filter"](a.get_text(" ", strip=True)):
            continue
        if href.startswith("/"):
            base = "/".join(source["url"].split("/")[:3])
            href = base + href
        # A NADA alterna entre /index.php/nada/... e /nada/...; trata como o mesmo link.
        href = href.replace("/index.php/", "/")
        href = re.sub(r"[?&]utm_[^#]*$", "", href)
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
            antigos = {it["href"] for it in state.get(name, {}).get("items", [])}
            novos = [it for it in items if it["href"] not in antigos] or items[:1]
            for it in novos[:3]:
                monitoramento.add_event(state, monitoramento.FONTES.get(name, (name,))[0], monitoramento._limpa(it["text"]), it["href"])
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
                subject="[Monitor] Atualização detectada (ANFAVEA/FENABRAVE/caminhões EUA)",
                body=body,
            )
            print("[INFO] E-mail enviado com sucesso.")
        except Exception as exc:
            print(f"[ERRO] Falha ao enviar e-mail: {exc}", file=sys.stderr)
            sys.exit(1)

    # Fontes que saíram da lista (ex.: NADA Market Beat de carros) não ficam no estado.
    nomes = {src["name"] for src in SOURCES}
    for k in [k for k in state if not k.startswith("_") and k not in nomes]:
        del state[k]
    save_state(state)
    monitoramento.write()


if __name__ == "__main__":
    main()
