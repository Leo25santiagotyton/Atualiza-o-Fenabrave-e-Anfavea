"""
Mercado de veículos usados e seminovos (FENAUTO)
------------------------------------------------
A FENABRAVE parou de publicar o "Informativo - Usados" em junho de 2025; o dado mensal de
transferências de usados e seminovos hoje sai nos press releases da FENAUTO (Federação
Nacional das Associações dos Revendedores de Veículos Automotores), no começo de cada mês,
com o resultado do mês anterior.

Lê a página de press releases, abre os textos de resultado mensal e extrai: total do mês,
variação sobre o mês anterior, acumulado do ano (e o do ano anterior), volume por segmento,
seminovos (0 a 3 anos) e os modelos mais negociados. Guarda o histórico em
alerts/usados_fenauto.json, que entra na aba Monitoramento (monitoramento.py).

Uso:
  python fenauto_usados.py              # atualiza o histórico
  python fenauto_usados.py --arquivo X  # lê o texto de um press release salvo (teste)
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from monitor import BROWSER_HEADERS

OUT = Path(__file__).parent / "alerts" / "usados_fenauto.json"
LISTA = "https://www.fenauto.org.br/news/categoria/press-releases"
BRT = timezone(timedelta(hours=-3))
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]
SEGMENTOS = {"automóveis": "Automóveis", "autos": "Automóveis", "comerciais leves": "Comerciais leves",
             "motos": "Motos", "comerciais pesados": "Comerciais pesados"}
NUM = r"(\d{1,3}(?:\.\d{3})+)"
PCT = r"([+\-−–]?\s?\d+(?:,\d+)?)\s?%"


def _n(s):
    return int(s.replace(".", ""))


def _p(s):
    return float(s.replace(" ", "").replace("−", "-").replace("–", "-").replace(",", "."))


def referencia(texto):
    """Mês de referência: o press release sai no começo do mês seguinte ("06 Outubro 2026" → setembro/2026)."""
    m = re.search(r"\b(\d{1,2}) (" + "|".join(MESES) + r") (\d{4})\b", texto, re.I)
    if not m:
        return None
    mes, ano = MESES.index(m.group(2).lower()) + 1, int(m.group(3))
    mes, ano = (12, ano - 1) if mes == 1 else (mes - 1, ano)
    return f"{ano}-{mes:02d}", int(m.group(1))


def parse(texto):
    """Números de um press release de resultado mensal; None se o texto não for desse tipo."""
    t = " ".join(texto.split())
    ref = referencia(t)
    if not ref:
        return None
    ref, _ = ref
    nome = MESES[int(ref[5:]) - 1]
    d = {"ref": ref, "mes": f"{nome}/{ref[:4]}"}
    # total do mês: número grande na mesma frase do nome do mês, fora das frases de acumulado
    for frase in re.split(r"(?<=[.!?])\s", t):
        if re.search(r"acumul|mesmo período|janeiro a|entre janeiro|primeiros", frase, re.I):
            continue
        for m in re.finditer(NUM + r"\s(?:de\s)?(?:unidades|veículos)", frase):
            v = _n(m.group(1))
            if v < 500_000:
                continue
            antes, depois = frase[:m.start()], frase[m.end():m.end() + 60]
            if re.search(r"\bcontra\b", antes[-25:], re.I) or re.search(r"\(\s*$", antes):
                continue
            if nome in (antes + depois).lower() or "total" not in d and re.search(r"comercializad|negociad|trocaram|registrou|Ao todo", frase, re.I):
                d.setdefault("total", v)
        m = re.search(r"contra\s" + NUM + r"\s(?:registrad[ao]s\s)?(?:em\s)?(" + "|".join(MESES) + r")", frase, re.I)
        if m and m.group(2).lower() != nome:
            d.setdefault("total_ant", _n(m.group(1)))
        m = re.search(r"superando os\s" + NUM + r"[^.]*?em\s(" + "|".join(MESES) + r")", frase, re.I)
        if m and m.group(2).lower() != nome:
            d.setdefault("total_ant", _n(m.group(1)))
        m = re.search(r"\(\s*" + NUM + r"\s*\)", frase)
        if m and "total_ant" not in d and re.search(r"em relação|recuo|sobre", frase, re.I):
            d["total_ant"] = _n(m.group(1))
    m = re.search(r"(?:acumul\w*|janeiro (?:e|a) \w+|primeiros \w+ meses)[^.]*?" + NUM + r"\s(?:de\s)?(?:unidades|veículos)", t, re.I)
    if m:
        d["acum"] = _n(m.group(1))
    m = re.search(r"contra\s" + NUM + r"\sno mesmo período", t, re.I)
    if m:
        d["acum_aa"] = _n(m.group(1))
    if d.get("acum") and d.get("acum_aa"):
        d["acum_var"] = round((d["acum"] / d["acum_aa"] - 1) * 100, 2)
    else:
        m = re.search(r"acumul.{0,250}?" + PCT, t, re.I)
        if m:
            d["acum_var"] = _p(m.group(1))
    if d.get("total") and d.get("total_ant"):
        d["mm"] = round((d["total"] / d["total_ant"] - 1) * 100, 2)
    m2 = re.search(r"(?:Comparativo|Quando confrontado)[^.]*?" + PCT, t, re.I)
    if m2:
        d["aa"] = _p(m2.group(1))
    seg = {}
    for m in re.finditer(r"(Automóveis|Autos|Comerciais Leves|Motos|Comerciais Pesados):\s" + NUM + r"\sunidades\s\(\s?" + PCT, t):
        seg[SEGMENTOS[m.group(1).lower()]] = {"unidades": _n(m.group(2)), "mm": _p(m.group(3))}
    if seg:
        d["segmentos"] = seg
    m = re.search(r"Seminovos\s\(0 a 3 anos\)[^.]*?" + PCT + r"[^.]*?" + NUM + r"\sunidades", t, re.I)
    if m:
        d["seminovos"] = {"mm": _p(m.group(1)), "unidades": _n(m.group(2))}
    m = re.search(r"(?:acumulado desse grupo|seminovos \(0 a 3 anos de uso\))[^.]*?" + PCT, t, re.I)
    if m:
        d.setdefault("seminovos", {})["acum_var"] = _p(m.group(1))
    lideres = {}
    for cat, pad in (("Automóveis", r"Automóveis:\s(?:O\s|A\s)?([^,.;]+?)\s(?:manteve|liderou|garantiu|segue|assumiu)[^.]*?" + NUM),
                     ("Comerciais leves", r"Comerciais Leves:\s(?:O\s|A\s)?(?:picape\s)?([^,.;]+?)\s(?:manteve|liderou|garantiu|segue|assumiu)[^.]*?" + NUM),
                     ("Motos", r"Motos:\s(?:O\s|A\s)?([^,.;]+?)\s(?:manteve|liderou|garantiu|segue|assumiu)[^.]*?" + NUM),
                     ("Comerciais pesados", r"Comerciais Pesados:\s(?:O\s|A\s)?(?:caminhão\s)?([^,.;]+?)\s(?:manteve|liderou|garantiu|segue|assumiu)[^.]*?" + NUM)):
        m = re.search(pad, t)
        if m:
            lideres[cat] = {"modelo": m.group(1).strip(), "unidades": _n(m.group(2))}
    if not lideres:  # formato "Autos VW Gol (67.461 unidades)" ou "AUTOS VW - GOL 70.874"
        for cat, rot in (("Automóveis", r"Autos"), ("Comerciais leves", r"Comerciais Leves"), ("Motos", r"Motos"), ("Comerciais pesados", r"Comerciais Pesados")):
            m = re.search(r"\b" + rot + r"\s([A-Z][\w\.]*(?:\s-)?\s[\w\-]+)\s\(?" + NUM, t, re.I)
            if m:
                lideres[cat] = {"modelo": m.group(1).replace(" - ", " ").strip(), "unidades": _n(m.group(2))}
    if lideres:
        d["lideres"] = lideres
    return d if d.get("total") or d.get("acum") else None


def coletar(s):
    urls = []
    for pag in (LISTA, LISTA + "?start=10", LISTA + "?start=20", LISTA + "?page=2", LISTA + "/page/2"):
        try:
            r = s.get(pag, timeout=40)
        except requests.RequestException as e:
            print(f"[AVISO] {pag}: {e}")
            continue
        if r.status_code != 200:
            continue
        for a in BeautifulSoup(r.text, "html.parser").find_all("a", href=True):
            h = requests.compat.urljoin(pag, a["href"])
            if "/news/" in h and "categoria" not in h and re.search(r"usad|semin|mercado|vend", h, re.I) and h not in urls:
                urls.append(h)
    meses = []
    for h in urls:
        try:
            r = s.get(h, timeout=40)
            texto = BeautifulSoup(r.text, "html.parser").get_text(" ")
        except requests.RequestException as e:
            print(f"[AVISO] {h}: {e}")
            continue
        d = parse(texto)
        if d:
            d["fonte"] = h
            meses.append(d)
            print(f"[INFO] {d['mes']}: total {d.get('total')}, acumulado {d.get('acum')} · {h}")
    return meses


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arquivo", help="texto de um press release salvo (teste do leitor)")
    args = ap.parse_args()
    if args.arquivo:
        print(json.dumps(parse(Path(args.arquivo).read_text(encoding="utf-8")), ensure_ascii=False, indent=1))
        return 0
    s = requests.Session()
    s.headers.update(BROWSER_HEADERS)
    novos = coletar(s)
    hist = {}
    if OUT.exists():
        hist = {m["ref"]: m for m in json.loads(OUT.read_text(encoding="utf-8")).get("meses", [])}
    for d in novos:
        hist[d["ref"]] = {**hist.get(d["ref"], {}), **d}
    # o total do mês anterior citado no release completa meses sem release lido
    for d in list(hist.values()):
        if d.get("total_ant"):
            a, m = int(d["ref"][:4]), int(d["ref"][5:])
            a, m = (a - 1, 12) if m == 1 else (a, m - 1)
            ref = f"{a}-{m:02d}"
            hist.setdefault(ref, {"ref": ref, "mes": f"{MESES[m - 1]}/{a}", "parcial": True}).setdefault("total", d["total_ant"])
    meses = sorted(hist.values(), key=lambda x: x["ref"], reverse=True)
    for i, d in enumerate(meses[:-1]):
        if d.get("total") and meses[i + 1].get("total") and "mm" not in d:
            d["mm"] = round((d["total"] / meses[i + 1]["total"] - 1) * 100, 2)
    if not meses:
        print("[ERRO] Nenhum resultado mensal lido da FENAUTO.", file=sys.stderr)
        return 1
    OUT.write_text(json.dumps({"updatedAt": datetime.now(BRT).isoformat(timespec="seconds"), "fonte": "FENAUTO (press releases)",
                               "meses": meses}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[INFO] {len(meses)} meses em {OUT.name}; último {meses[0]['mes']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
