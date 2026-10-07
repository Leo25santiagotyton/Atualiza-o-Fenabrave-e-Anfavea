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

FONTES = {
    "ANFAVEA - Edições em PDF (Carta da Anfavea)": ("ANFAVEA", "https://anfavea.com.br/site/conteudos/carta-da-anfavea/"),
    "FENABRAVE - Imprensa (releases mensais)": ("FENABRAVE", "https://www.fenabrave.org.br/portalv2/home/imprensa"),
    "NADA Market Beat (EUA - vendas mensais)": ("NADA (EUA)", "https://www.nada.org/nada/market-beat"),
    "Alliance for Automotive Innovation - Market Reports (EUA)": ("Auto Innovators (EUA)", "https://www.autosinnovate.org/resources/market-reports"),
}


def _read(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _limpa(t):
    """Separa a data colada no fim do título (FENABRAVE) e o rótulo repetido da NADA."""
    t = re.sub(r"\s+", " ", t).strip()
    m = re.match(r"^(.*\S)\s*(\d{2}/\d{2}/\d{4})$", t)
    if m:
        t = m.group(1) + " · " + m.group(2)
    t = re.sub(r"^Papers Reports", "", t)
    t = re.sub(r"^(\w+ \d{1,2}, \d{4})(?:NADA Market Beat)*:?\s*", r"\1 · ", t)
    return t


def add_event(fonte, titulo, link=""):
    """Registra um aviso de novidade (repete o mesmo título/link só uma vez)."""
    d = _read(OUT)
    ev = d.get("eventos", [])
    eid = hashlib.sha1(f"{fonte}|{titulo}|{link}".encode()).hexdigest()[:12]
    if any(e.get("id") == eid for e in ev):
        return
    now = datetime.now(BRT)
    ev.insert(0, {"id": eid, "at": now.isoformat(timespec="seconds"), "label": now.strftime("%d/%m %H:%M"),
                  "fonte": fonte, "titulo": titulo, "link": link})
    d["eventos"] = ev[:MAX_EVENTOS]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def write():
    d = _read(OUT)
    setor = _read(SETOR)
    mon = _read(MONITOR)
    fontes = []
    for chave, (nome, url) in FONTES.items():
        itens = []
        for it in (mon.get(chave) or {}).get("items", []):
            t = _limpa(it.get("text", ""))
            if len(t) >= 25:  # descarta links genéricos ("Market Reports", "view the report")
                itens.append({"text": t, "href": it.get("href", "")})
        fontes.append({"nome": nome, "url": url, "itens": itens[:5]})
    now = datetime.now(BRT)
    d.update(updatedAt=now.isoformat(timespec="seconds"), updatedLabel=now.strftime("%d/%m/%Y %H:%M"),
             fenabrave=setor.get("fenabrave"), anfavea=setor.get("anfavea"), fontes=fontes)
    d.setdefault("eventos", [])
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    write()
