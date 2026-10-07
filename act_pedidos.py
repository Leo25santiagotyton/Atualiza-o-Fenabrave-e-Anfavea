"""
Pedidos de caminhões nos EUA (ACT Research) por classe
------------------------------------------------------
Lê as notícias de pedidos listadas na página de manchetes da ACT Research
(trends-headlines), tira de cada uma o número do mês (Classe 8 e Classes 5-7,
preliminar ou final) e atualiza alerts/act_pedidos.json, que a aba
Monitoramento do painel mostra. O número preliminar da Classe 8 da FTR, quando
aparece nas mesmas notícias, fica guardado só para comparação.

Regras: o número final substitui o preliminar; um preliminar nunca substitui um
final; valores fora de 1.000–80.000 unidades são ignorados. Quando há números
diferentes para o mesmo mês, vale o que aparece em mais notícias.

Roda dentro do monitor.py (que manda o e-mail); sozinho só mostra o que mudaria:
  python act_pedidos.py
"""

import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ARQ = Path(__file__).parent / "alerts" / "act_pedidos.json"
LISTA = "https://www.actresearch.net/resources/trends-headlines"
BRT = timezone(timedelta(hours=-3))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}
MESES_EN = ["january", "february", "march", "april", "may", "june", "july",
            "august", "september", "october", "november", "december"]
MESES_PT = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
RE_MES = re.compile(r"\b(" + "|".join(MESES_EN) + r")\b", re.I)
RE_NUM = re.compile(r"\b(\d{1,2},\d{3})\b(?!\s*%)")
# verbo de resultado: evita pegar chamadas de outras matérias ("Class 8 Net Orders for September at 21,300 Units")
RE_VERBO = re.compile(r"\b(total(?:ed|ing|led)|reach(?:ed|ing)|r[io]se?n?|rising|climb\w*|gr[eo]w\w*|increas\w*|jump\w*|fared|fell|fall(?:ing)?|dropp?(?:ed|ing)?|"
                      r"declin(?:ed|ing)|slid|came in|were|was|counted|put)\b", re.I)


def _ler():
    try:
        return json.loads(ARQ.read_text(encoding="utf-8"))
    except Exception:
        return {}


RE_CLS = re.compile(r"classes?\s*5\s*[-–]\s*[78]|class\s*8", re.I)
RE_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*(?:y/y|year[- ]over[- ]year|annually|from a year|compared to (?:the same|a year))", re.I)
RE_NEG = re.compile(r"\b(down|fell|fall|declin\w*|dropp?\w*|slid|slide|lower|decrease\w*)\b", re.I)


def _ano(mes, hoje):
    """Mês sem ano na notícia: o mais recente que já passou."""
    return hoje.year if mes < hoje.month or (mes == hoje.month and hoje.day > 1) else hoje.year - 1


def _segmentos(frase):
    """Divide a frase em trechos que começam numa menção de classe (Class 8, Classes 5-7)."""
    ms = list(RE_CLS.finditer(frase))
    for k, m in enumerate(ms):
        fim = ms[k + 1].start() if k + 1 < len(ms) else len(frase)
        txt = m.group(0).lower()
        if re.search(r"5\s*[-–]\s*8", txt):
            continue  # total 5-8, não serve
        yield ("Classes 5-7" if "5" in txt else "Classe 8"), frase[m.start():fim]


def extrai(texto, titulo, hoje):
    """Devolve tuplas (fonte, classe, 'AAAA-MM', valor, status, var_aa) achadas no texto de uma notícia.
    var_aa é a variação anual citada junto do número (para conferir), ou None."""
    achados = []
    pre_tit = "prelim" in titulo.lower()
    tem_act = "ACT" in texto
    for frase in re.split(r"(?<=[.!?])\s+(?=[A-Z])", texto):
        if len(frase) > 450 or not RE_VERBO.search(frase):
            continue
        mm = RE_MES.search(frase)
        if not mm:
            continue
        mes = MESES_EN.index(mm.group(1).lower()) + 1
        ya = re.match(r"\s*,?\s*(20\d\d)", frase[mm.end():])
        ym = f"{int(ya.group(1)) if ya else _ano(mes, hoje)}-{mes:02d}"
        low = frase.lower()
        status = "final" if "final" in low else "prelim" if ("prelim" in low or pre_tit) else "?"
        tem_ftr = bool(re.search(r"\bFTR\b", frase))
        for cl, seg in _segmentos(frase):
            nums = list(RE_NUM.finditer(seg))
            for k, nn in enumerate(nums):
                lo = nums[k - 1].end() if k else 0
                hi = nums[k + 1].start() if k + 1 < len(nums) else len(seg)
                valor = int(nn.group(1).replace(",", ""))
                if not 1000 <= valor <= 80000:
                    continue
                # a fonte é a menção (ACT ou FTR) mais próxima antes do número; sem menção antes, é ACT
                abs_pos = frase.find(seg) + nn.start()
                antes = [(m.start(), m.group(0)) for m in re.finditer(r"\b(ACT|FTR)\b", frase[:abs_pos])]
                fonte = antes[-1][1] if antes else "ACT"
                if (fonte == "ACT" and not tem_act) or (fonte == "FTR" and cl != "Classe 8"):
                    continue
                # variação anual citada perto do número (para conferir), depois da menção da fonte
                ms = [m.end() for m in re.finditer(r"\b(ACT|FTR)\b", seg[:nn.start()])]
                lo = max([lo] + ms)
                var, dist = None, 999
                for pm in RE_PCT.finditer(seg, lo, hi):
                    dd = abs(pm.start() - nn.start())
                    if dd < dist and dd < 120:
                        jan = seg[max(0, pm.start() - 40):pm.start()] + seg[pm.end():pm.end() + 12]
                        var, dist = float(pm.group(1)) * (-1 if RE_NEG.search(jan) else 1), dd
                achados.append((fonte, cl, ym, valor, status if fonte == "ACT" else "prelim", var))
                if not tem_ftr:
                    break
    return achados


def coleta(hoje=None):
    hoje = hoje or datetime.now(BRT)
    s = requests.Session()
    s.headers.update(UA)
    soup = BeautifulSoup(s.get(LISTA, timeout=30).text, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        t = a.get_text(" ", strip=True)
        href = re.sub(r"[?&]utm_[^#]*$", "", a["href"])
        if href.startswith("http") and re.search(r"order", t, re.I) and re.search(r"class", t, re.I) and href not in [x[1] for x in links]:
            links.append((t, href))
    achados = []
    for titulo, href in links[:15]:
        try:
            r = s.get(href, timeout=30)
            if r.status_code != 200:
                continue
            texto = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
        except Exception:
            continue
        for a in extrai(texto, titulo, hoje):
            achados.append(a + (href,))
    return achados


def atualiza(achados=None):
    """Aplica os números novos em alerts/act_pedidos.json. Devolve uma lista de
    avisos (texto, link) com o que mudou, para o e-mail e o painel."""
    d = _ler()
    if not d.get("classes"):
        return []
    achados = coleta() if achados is None else achados
    prelim = d.setdefault("preliminar", {})
    if isinstance(prelim, list):  # formato antigo: lista única para as duas classes
        prelim = d["preliminar"] = {k: list(prelim) for k in d["classes"]}
    ftr = d.setdefault("ftr", {})
    avisos = []
    # voto: para cada (classe, mês, status) vale o número mais citado
    votos = {}
    for fonte, cl, ym, v, st, var, href in achados:
        # confere com a variação anual citada na própria notícia (pega erro de digitação)
        ano_i, mes_i = ym.split("-")
        base = d["classes"].get(cl, {}).get(str(int(ano_i) - 1), [])
        b0 = base[int(mes_i) - 1] if int(mes_i) - 1 < len(base) else None
        if var is not None and b0 and abs((v / b0 - 1) * 100 - var) > 2:
            continue
        if fonte == "FTR":
            if ftr.get(cl, {}).get(ym) != v:
                ftr.setdefault(cl, {})[ym] = v
            continue
        votos.setdefault((cl, ym, st), Counter())[(v, href)] += 1
    escolha = {}
    for (cl, ym, st), c in votos.items():
        tot = Counter()
        for (v, _), n in c.items():
            tot[v] += n
        v = tot.most_common(1)[0][0]
        href = next(h for (vv, h) in c if vv == v)
        escolha[(cl, ym, st)] = (v, href)
    for (cl, ym, st), (v, href) in sorted(escolha.items()):
        if st == "?" and (cl, ym, "final") in escolha or st == "?" and (cl, ym, "prelim") in escolha:
            continue
        if st == "prelim" and (cl, ym, "final") in escolha:
            continue
        serie = d["classes"].get(cl)
        if not serie:
            continue
        hj = datetime.now(BRT)
        if (hj.year * 12 + hj.month) - (int(ym[:4]) * 12 + int(ym[5:])) > 4:
            continue  # só mexe nos meses recentes; o histórico vem da planilha
        ano, mes = ym.split("-")
        lst = serie.setdefault(ano, [])
        i = int(mes) - 1
        if i > len(lst):
            continue  # falta mês anterior; não deixa buraco na série
        era_prelim = ym in prelim.get(cl, [])
        atual = lst[i] if i < len(lst) else None
        if st == "final" or (st == "?" and atual is not None and era_prelim):
            if atual == v and not era_prelim:
                continue
            if st == "?" and atual == v:
                continue
            novo_status = "final" if st == "final" else "prelim"
        else:  # preliminar (ou sem rótulo) só entra se o mês ainda não tem número final
            if atual is not None and not era_prelim:
                continue
            if atual == v:
                continue
            novo_status = "prelim"
        if i == len(lst):
            lst.append(v)
        else:
            lst[i] = v
        p = prelim.setdefault(cl, [])
        if novo_status == "prelim" and ym not in p:
            p.append(ym)
        if novo_status == "final" and ym in p:
            p.remove(ym)
        ant = d["classes"][cl].get(str(int(ano) - 1), [])
        aa = f" ({(v / ant[i] - 1) * 100:+.0f}% a/a)".replace(".", ",") if i < len(ant) and ant[i] else ""
        rot = "preliminar" if novo_status == "prelim" else "final"
        avisos.append((f"{cl} {MESES_PT[i]}/{ano} {rot}: {v:,} pedidos{aa}".replace(",", "."), href))
    if avisos or achados:
        hoje = datetime.now(BRT)
        d["atualizado"] = hoje.strftime("%d/%m/%Y")
        d["fonte"] = "ACT Research (notícias de pedidos mensais; planilha ACT_Research_August.xlsx como base)"
        ARQ.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return avisos


if __name__ == "__main__":
    for a in coleta():
        print(a)
