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
FIPE = ROOT / "alerts" / "fipe_resumo.json"  # resumo mensal da Tabela FIPE (fipe_mensal.py)
CRED = ROOT / "alerts" / "credito_veiculos.json"  # crédito para veículos (credito_veiculos.py)
SEMI = ROOT / "alerts" / "seminovos_resumo.json"  # radar de seminovos Movida, Localiza e Turbi (seminovos_radar.py)
CAMIN = ROOT / "alerts" / "caminhoes_resumo.json"  # caminhões seminovos Vamos e VolksConfia (seminovos_radar.py --segmento caminhoes)
USADOS = ROOT / "alerts" / "usados_fenauto.json"  # mercado de usados e seminovos, press releases da FENAUTO (fenauto_usados.py)
CHUVA = ROOT / "alerts" / "chuva_priner.json"  # chuva × Priner, visão mensal (chuva_priner.py)
IMPL = ROOT / "alerts" / "implementos.json"  # implementos rodoviários: ANFIR e Comex Stat de reboques/semirreboques (implementos.py)
ACT = ROOT / "alerts" / "act_pedidos.json"  # pedidos de caminhões nos EUA por classe (planilha da ACT, atualizada à mão)
BRT = timezone(timedelta(hours=-3))
MAX_EVENTOS = 40
GENERICOS = {"nada market beat", "atd truck beat", "market reports", "prior economic impact reports", "view the report"}

FONTES = {
    "ANFAVEA - Edições em PDF (Carta da Anfavea)": ("ANFAVEA", "https://anfavea.com.br/site/conteudos/carta-da-anfavea/"),
    "FENABRAVE - Imprensa (releases mensais)": ("FENABRAVE", "https://www.fenabrave.org.br/portalv2/home/imprensa"),
    "FRED - vendas de caminhões pesados (EUA)": ("FRED · vendas heavy trucks (EUA)", "https://fred.stlouisfed.org/series/HTRUCKSSAAR"),
    "ACT Research - pedidos de caminhões (EUA)": ("ACT Research · pedidos (EUA)", "https://www.actresearch.net/resources/trends-headlines"),
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


def _evento_fipe(f):
    """Aviso de tabela FIPE nova, tirado do próprio resumo (fipe_resumo.json): um por mês de
    referência, com a hora em que o resumo foi gerado, para não depender de outro estado."""
    if not f or not f.get("ref") or not f.get("gerado_em"):
        return []
    at = datetime.fromisoformat(f["gerado_em"])
    titulo = f"Tabela de {f.get('mes', '')} publicada — " + (f.get("resumo") or "").split(". ")[0].rstrip(".")
    return [{"id": hashlib.sha1(f"FIPE|{f['ref']}".encode()).hexdigest()[:12], "at": at.isoformat(timespec="seconds"),
             "label": at.strftime("%d/%m %H:%M"), "fonte": "FIPE", "titulo": titulo,
             "link": "https://veiculos.fipe.org.br/"}]


def _slim_impl(im):
    """Painel: sem o detalhe por família de cada acumulado (só o último e o do mesmo período do ano anterior)."""
    if not im:
        return None
    out = dict(im)
    a = dict(im.get("anfir") or {})
    acum = a.pop("acum", {}) or {}
    if a.get("ultimo") in acum:
        a["atual"] = acum[a["ultimo"]]
    out["anfir"] = a
    return out


def _evento_anfir(im):
    """Aviso de relatório novo da ANFIR (um por período), com a hora em que o implementos.py viu."""
    a = (im or {}).get("anfir") or {}
    ult, quando = a.get("ultimo"), a.get("novo_em")
    if not ult or not quando:
        return []
    m = next((x for x in a.get("meses", []) if x["mes"] == ult), {})
    at = datetime.fromisoformat(quando)
    titulo = (a.get("titulo") or f"Emplacamentos até {ult}") + (
        f" — reboques e semirreboques no mês: {m['reb']:,}".replace(",", ".") if m.get("reb") is not None else "")
    return [{"id": hashlib.sha1(f"ANFIR|{ult}".encode()).hexdigest()[:12], "at": at.isoformat(timespec="seconds"),
             "label": at.strftime("%d/%m %H:%M"), "fonte": "ANFIR", "titulo": titulo, "link": a.get("url") or ""}]


MES_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _ml(ym):
    return f"{MES_PT[int(ym[5:7]) - 1]}/{ym[2:4]}"


def _pct(a, b):
    return f"{(a / b - 1) * 100:+.1f}%".replace(".", ",") if a is not None and b else "–"


def _eventos_mensais(cred, chuva, vistos, agora):
    """Avisos de dado mensal novo (crédito auto B3/Trillia e BC, chuva mensal nos pontos da Priner).
    A hora do aviso é a da primeira vez em que o mês apareceu (guardada em `vistos`)."""
    out = []

    def ev(chave, fonte, titulo, link):
        eid = hashlib.sha1(chave.encode()).hexdigest()[:12]
        at = datetime.fromisoformat(vistos.setdefault(eid, agora.isoformat(timespec="seconds")))
        out.append({"id": eid, "at": at.isoformat(timespec="seconds"), "label": at.strftime("%d/%m %H:%M"),
                    "fonte": fonte, "titulo": titulo, "link": link})

    b3 = (cred or {}).get("b3") or {}
    if b3:
        ym = max(b3)
        v, aa = b3[ym], b3.get(f"{int(ym[:4]) - 1}{ym[4:]}") or {}
        tipos = " · ".join(f"{n} {v[k] / 1000:,.0f} mil".replace(",", ".") for k, n in (("leves", "leves"), ("motos", "motos"), ("pesados", "pesados")) if v.get(k))
        ev(f"CRED-B3|{ym}", "Crédito auto · B3/Trillia",
           f"{_ml(ym)}: " + f"{v.get('total', 0) / 1000:,.0f}".replace(",", ".") + f" mil veículos financiados ({_pct(v.get('total'), aa.get('total'))} a/a)" + (f" — {tipos}" if tipos else ""),
           v.get("url") or "https://www.b3.com.br/pt_br/noticias/")
    m = (cred or {}).get("mensal") or {}
    if m.get("meses"):
        ym = m["meses"][-1]
        i_aa = m["meses"].index(f"{int(ym[:4]) - 1}{ym[4:]}") if f"{int(ym[:4]) - 1}{ym[4:]}" in m["meses"] else None
        cp = (m.get("conc_pf") or [None])[-1]
        cpa = m["conc_pf"][i_aa] if i_aa is not None and m.get("conc_pf") else None
        tx, inad = (m.get("taxa_pf") or [None])[-1], (m.get("inad_pf") or [None])[-1]
        partes = []
        if cp is not None:
            partes.append(f"concessões PF R$ {cp / 1000:.1f} bi ({_pct(cp, cpa)} a/a)".replace(".", ","))
        if tx is not None:
            partes.append(f"taxa PF {tx:.1f}".replace(".", ",") + "% a.a.")
        if inad is not None:
            partes.append(f"inadimplência PF {inad:.2f}%".replace(".", ","))
        ev(f"CRED-BC|{ym}", "Crédito auto · Banco Central", f"{_ml(ym)}: " + " · ".join(partes), "https://www3.bcb.gov.br/sgspub/")
    mens = (chuva or {}).get("mensal") or {}
    sites = (chuva or {}).get("sites") or []
    if mens.get("meses") and len(mens.get("sites", [])) == len(sites):
        ym, mes = mens["meses"][-1], int(mens["meses"][-1][5:7])
        t = w = tn = 0.0
        for s, ms in zip(sites, mens["sites"]):
            v, nm, p = ms["hist"][-1], ms["normal"][mes - 1], s.get("peso", 1)
            if v is not None and nm is not None:
                t, tn, w = t + v * p, tn + nm * p, w + p
        if w:
            ev(f"CHUVA|{ym}", "Chuva × Priner",
               f"{_ml(ym)} fechou com {t / w:.0f} mm em média nos pontos da Priner (ponderado pela relevância), {_pct(t, tn)} contra o normal do mês",
               "https://open-meteo.com/")
    return out


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
             fenabrave=setor.get("fenabrave"), anfavea=setor.get("anfavea"), fontes=fontes, act=_read(ACT) or None, fipe=_read(FIPE) or None,
             credito=_read(CRED) or None, seminovos=_read(SEMI) or None, caminhoes=_read(CAMIN) or None, usados=_read(USADOS) or None,
             implementos=_slim_impl(_read(IMPL)))
    vistos = d.get("_vistos") or {}
    mensais = _eventos_mensais(_read(CRED), _read(CHUVA), vistos, now)
    d["_vistos"] = vistos
    ev = {e["id"]: e for e in (setor.get("_eventos", []) + mon.get("_eventos", []) + _evento_fipe(d.get("fipe")) + _evento_anfir(_read(IMPL)) + mensais)}
    d["eventos"] = sorted(ev.values(), key=lambda e: e["at"], reverse=True)[:MAX_EVENTOS]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    write()
