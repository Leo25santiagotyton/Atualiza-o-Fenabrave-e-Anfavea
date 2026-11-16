"""
Caminhões por marca e por modelo (FENABRAVE)
--------------------------------------------
O Informativo mensal de Emplacamentos da FENABRAVE (um PDF por mês, /portal/files/AAAA_MM_xx.pdf) traz:
  - "Ranking por marca <Mês>/<Ano>": caminhões (e ônibus) por fabricante no mês e no acumulado do ano;
  - "Modelos mais emplacados acumulado até <Mês>/<Ano>": top 10 modelos de caminhão por subsegmento
    (semileve, leve, médio, semipesado e pesado), com os dois últimos meses e o acumulado.

Este script lê todos os PDFs que a página de emplacamentos lista (e tenta os de anos anteriores pelo mesmo
padrão de nome), guarda o histórico mês a mês por marca e por modelo e marca as fabricantes chinesas.
Grava alerts/caminhoes_marcas.json, que vai para o painel (aba Monitoramento → CAMINHÕES · MARCAS).

Uso:
  python caminhoes_marcas.py            # só lê PDFs ainda não lidos
  python caminhoes_marcas.py --refazer  # relê tudo
"""

import argparse
import io
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pdfplumber
import requests
from bs4 import BeautifulSoup

from relatorios_setor import FENABRAVE_HOME, FENABRAVE_PAGE, MESES, session

OUT = Path(__file__).parent / "alerts" / "caminhoes_marcas.json"
BRT = timezone(timedelta(hours=-3))
ANO_INI = 2021
FILES = "https://www.fenabrave.org.br/portal/files/"
# fabricantes chinesas (ou marcas de grupos chineses) que aparecem ou podem aparecer no ranking de caminhões
CHINESAS = {"FOTON", "JAC", "SINOTRUK", "CNHTC", "SITRAK", "SHACMAN", "XCMG", "SANY", "NANJING", "BYD", "CRRC",
            "HIGER", "FAW", "JMC", "DONGFENG", "CHERY", "WINDROSE", "GWM", "KING LONG", "YUTONG", "SHAANXI",
            "HOWO", "CAMC", "BEIBEN", "JMEV", "ZHONGTONG", "GOLDEN DRAGON", "ZOOMLION", "LIUGONG", "SDLG",
            "HAVAL", "GREAT WALL", "KAIYUN", "CHANGAN", "DFSK", "JINBEI", "EUROFOTON"}
SEGS = {"SEMI-LEVE": "Semileve", "SEMILEVE": "Semileve", "LEVE": "Leve", "MÉDIO": "Médio", "MEDIO": "Médio",
        "SEMIPESADO": "Semipesado", "SEMI-PESADO": "Semipesado", "PESADO": "Pesado"}
LINHA_MARCA = re.compile(r"^(\d+)º\s+(.+?)\s+(\d{1,3}(?:\.\d{3})*)\s+(\d+,\d+)%")


def _int(s):
    s = s.strip()
    if not s or s in ("=", "-"):
        return None
    if re.fullmatch(r"0,0+", s):
        return 0
    return int(s.replace(".", "")) if re.fullmatch(r"\d{1,3}(?:\.\d{3})*", s) else None


def chinesa(marca):
    m = marca.upper()
    return any(m == c or m.startswith(c + " ") or m.startswith(c + "/") for c in CHINESAS)


def periodo(texto):
    m = re.search(r"Ranking por marca\s+([A-Za-zçÇ]+)\s*/\s*(\d{4})", texto, re.I)
    if not m or m.group(1).lower() not in MESES:
        return None
    return f"{m.group(2)}-{MESES.index(m.group(1).lower()) + 1:02d}"


def parse_ranking(texto):
    """Coluna da esquerda (caminhões) do ranking: mês (antes de 'Acumulado') e acumulado do ano."""
    mes, acum, alvo = {}, {}, None
    for ln in texto.splitlines():
        ln = " ".join(ln.split())
        if re.match(r"^Ranking por marca", ln, re.I):
            alvo = mes
            continue
        if re.match(r"^Acumulado\b", ln, re.I):
            alvo = acum
            continue
        m = LINHA_MARCA.match(ln)
        if m and alvo is not None:
            alvo[m.group(2).strip()] = _int(m.group(3))
    return mes, acum


def parse_modelos(textos):
    """Páginas 'Modelos mais emplacados' de caminhões: {segmento: {modelo: [mês anterior, mês, acumulado]}}."""
    out, seg = {}, None
    for texto in textos:
        for ln in texto.splitlines():
            ln = " ".join(ln.split())
            if ln.upper() in SEGS:
                seg = SEGS[ln.upper()]
                out.setdefault(seg, {})
                continue
            if re.match(r"^(ÔNIBUS|ONIBUS|AUTOM[ÓO]VEIS|COMERCIAIS)", ln, re.I):
                seg = None
                continue
            m = re.match(r"^\d+º\s+(.+)$", ln)
            if not m or seg is None:
                continue
            t = m.group(1).split()
            if len(t) < 4 or not t[-1].endswith("%"):
                continue
            acum = _int(t[-2])
            nums, i = [], len(t) - 3
            while i >= 0 and len(nums) < 2:
                tok = t[i]
                if tok in ("=", "▲", "▼", "↑", "↓"):
                    i -= 1
                    continue
                v = _int(tok)
                if v is None:
                    break
                nums.append(v)
                i -= 1
            if acum is None or len(nums) < 2:
                continue
            nome = " ".join(t[:i + 1]).strip()
            if nome:
                out[seg][nome] = [nums[1], nums[0], acum]
    return {k: v for k, v in out.items() if v}


def ler_pdf(s, url):
    r = s.get(url, timeout=120)
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        return None
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        n = len(pdf.pages)
        textos = {}

        def txt(i):
            if i not in textos:
                textos[i] = pdf.pages[i].extract_text() or ""
            return textos[i]

        # o ranking costuma ficar no último terço; procura de trás para a frente
        rk, mes, acum = None, {}, {}
        for i in range(n - 1, -1, -1):
            if re.search(r"Ranking por marca", txt(i), re.I) and re.search(r"CAMINH", txt(i)):
                m1, a1 = parse_ranking(txt(i))
                if len(m1) > len(mes):
                    rk, mes, acum = i, m1, a1
                if len(m1) >= 5:
                    break
        if rk is None:
            return None
        per = periodo(txt(rk))
        paginas = [txt(i) for i in range(rk + 1, min(n, rk + 5))
                   if re.search(r"Modelos mais emplacados", txt(i), re.I)
                   and re.search(r"(Semi-?Leve|Semi-?pesado|Pesado|M[ée]dio)", txt(i), re.I)]
        modelos = parse_modelos(paginas)
    return {"periodo": per, "marcas": mes, "acum": acum, "modelos": modelos}


def lista_pdfs(s):
    try:
        s.get(FENABRAVE_HOME, timeout=30)
    except Exception:  # noqa: BLE001
        pass
    r = s.get(FENABRAVE_PAGE, timeout=40)
    r.raise_for_status()
    out = {}
    for a in BeautifulSoup(r.text, "html.parser").find_all("a", href=True):
        h = a["href"].strip()
        m = re.search(r"/portal/files/(\d{4})_(\d{2})_[^/]*\.pdf$", h, re.I)
        if m:
            out[f"{m.group(1)}-{m.group(2)}"] = requests.compat.urljoin(FENABRAVE_PAGE, h)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refazer", action="store_true")
    args = ap.parse_args()
    base = {} if args.refazer or not OUT.exists() else json.loads(OUT.read_text(encoding="utf-8"))
    meses = {m["mes"]: m for m in base.get("meses", [])}
    sem_pdf = set(base.get("sem_pdf", []))
    s = session()
    lista = lista_pdfs(s)
    hoje = datetime.now(BRT)
    # meses anteriores à lista da página: tenta o mesmo padrão de nome
    candidatos = dict(lista)
    a, m = ANO_INI, 1
    while (a, m) < (hoje.year, hoje.month):
        k = f"{a}-{m:02d}"
        if k not in candidatos and k not in sem_pdf:
            candidatos[k] = [f"{FILES}{a}_{m:02d}_02.pdf", f"{FILES}{a}_{m:02d}_01.pdf", f"{FILES}{a}_{m:02d}.pdf"]
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    novos = 0
    for k in sorted(candidatos):
        urls = candidatos[k] if isinstance(candidatos[k], list) else [candidatos[k]]
        if k in meses and meses[k].get("url") in urls and len(meses[k].get("marcas", {})) >= 5:
            continue
        d = None
        for u in urls:
            try:
                d = ler_pdf(s, u)
            except Exception as exc:  # noqa: BLE001
                print(f"[AVISO] {k} {u}: {exc}")
                d = None
            if d:
                d["url"] = u
                break
        if not d:
            if isinstance(candidatos[k], list):
                sem_pdf.add(k)
            else:
                print(f"[AVISO] {k}: não li o ranking de caminhões em {urls[0]}")
            continue
        per = d.pop("periodo") or k
        if len(d["marcas"]) < 5:
            meses.pop(per, None)
            print(f"[AVISO] {per}: ranking sem marcas ({d['url']})")
            continue
        meses[per] = {"mes": per, **d, "total": sum(v for v in d["marcas"].values() if v)}
        sem_pdf.discard(per)
        novos += 1
        ch = sum(v for mm, v in d["marcas"].items() if v and chinesa(mm))
        print(f"[INFO] {per}: {len(d['marcas'])} marcas, total {meses[per]['total']}, chinesas {ch}, "
              f"modelos {sum(len(x) for x in d['modelos'].values())}")
    todas = sorted({mm for x in meses.values() for mm in x["marcas"]})
    out = {"meses": [meses[k] for k in sorted(meses)],
           "chinesas": [mm for mm in todas if chinesa(mm)],
           "sem_pdf": sorted(sem_pdf),
           "fonte": FENABRAVE_PAGE,
           "gerado_em": datetime.now(BRT).isoformat(timespec="seconds")}
    if novos or not OUT.exists() or args.refazer:
        OUT.parent.mkdir(exist_ok=True)
        OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"[OK] caminhões por marca: {len(out['meses'])} meses ({out['meses'][0]['mes'] if out['meses'] else '-'}"
          f" a {out['meses'][-1]['mes'] if out['meses'] else '-'}), {novos} novos; chinesas: {', '.join(out['chinesas'])}")


if __name__ == "__main__":
    main()
