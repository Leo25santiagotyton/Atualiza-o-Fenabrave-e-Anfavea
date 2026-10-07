"""
Monitoramento (aba do painel)
-----------------------------
Junta num só arquivo, alerts/monitoramento.json, o que o painel mostra na aba
"Monitoramento": as tabelas da FENABRAVE e da ANFAVEA (de alerts/setor_state.json),
os últimos itens de cada fonte acompanhada pelo monitor (state.json) e a lista de
avisos de novidade. Cada aviso tem um id; o painel usa o id para disparar a
notificação uma única vez.

  python monitoramento.py      # só regrava o arquivo a partir dos estados atuais
"""

import hashlib
import re
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "alerts" / "monitoramento.json"
SETOR = ROOT / "alerts" / "setor_state.json"
MONITOR = ROOT / "state.json"
BRT = timezone(timedelta(hours=-3))
MAX_EVENTOS = 40
GENERICOS = {"nada market beat", "atd truck beat", "market reports", "prior economic impact reports", "view the report"}

FONTES = {
    "ANFAVEA - Edições em PDF (Carta da Anfavea)": ("ANFAVEA", "https://anfavea.com.br/site/conteudos/carta-da-anfavea/"),
    "FENABRAVE - Imprensa (releases mensais)": ("FENABRAVE", "https://www.fenabrave.org.br/portalv2/home/imprensa"),
    "ATD Truck Beat (EUA - vendas de caminhões)": ("ATD Truck Beat (EUA)", "https://www.nada.org/atd/research/truck-beat"),
    "ACT Research - pedidos de caminhões (EUA)": ("ACT Research (EUA)", "https://www.actresearch.net/resources/trends-headlines"),
}


def _read(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _limpa(t):
    """Separa a data colada no fim do título (FENABRAVE) e o rótulo repetido do ATD Truck Beat."""
    t = re.sub(r"\s+", " ", t).strip()
    m = re.match(r"^(.*\S)\s*(\d{2}/\d{2}/\d{4})$", t)
    if m:
        t = m.group(1) + " · " + m.group(2)
    t = re.sub(r"^Papers Reports", "", t)
    t = re.sub(r"^(\w+ \d{1,2}, \d{4})(?:ATD Truck Beat|NADA Market Beat)*:?\s*", r"\1 · ", t)
    return t


def add_event(state, fonte, titulo, link=""):
    """Registra um aviso de novidade dentro do estado da própria fonte (state.json do
    monitor ou setor_state.json dos relatórios), assim cada workflow só grava o seu
    arquivo e o monitoramento.json pode ser refeito a qualquer momento sem perder nada."""
    ev = state.setdefault("_eventos", [])
    eid = hashlib.sha1(f"{fonte}|{titulo}|{link}".encode()).hexdigest()[:12]
    if any(e.get("id") == eid for e in ev):
        return
    now = datetime.now(BRT)
    ev.insert(0, {"id": eid, "at": now.isoformat(timespec="seconds"), "label": now.strftime("%d/%m %H:%M"),
                  "fonte": fonte, "titulo": titulo, "link": link})
    del ev[MAX_EVENTOS:]


def write():
    d = _read(OUT)
    setor = _read(SETOR)
    mon = _read(MONITOR)
    fontes = []
    for chave, (nome, url) in FONTES.items():
        itens = []
        for it in (mon.get(chave) or {}).get("items", []):
            t, href = _limpa(it.get("text", "")), it.get("href", "")
            if t.lower() in GENERICOS or len(t) < 4:
                continue
            m = re.search(r"carta(\d+)\.pdf", href, re.I)
            if m:
                t = f"Carta {m.group(1)} · {t}"
            itens.append({"text": t, "href": href})
        fontes.append({"nome": nome, "url": url, "itens": itens[:5]})
    now = datetime.now(BRT)
    d.update(updatedAt=now.isoformat(timespec="seconds"), updatedLabel=now.strftime("%d/%m/%Y %H:%M"),
             fenabrave=setor.get("fenabrave"), anfavea=setor.get("anfavea"), fontes=fontes)
    ev = {e["id"]: e for e in (setor.get("_eventos", []) + mon.get("_eventos", []))}
    d["eventos"] = sorted(ev.values(), key=lambda e: e["at"], reverse=True)[:MAX_EVENTOS]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    write()
