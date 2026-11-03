"""
Crédito para veículos (aba Monitoramento do painel)
---------------------------------------------------
Junta em alerts/credito_veiculos.json:

- Banco Central, séries mensais do SGS (nota de crédito, sai no fim do mês
  seguinte): taxa média de juros, concessões (volume financiado no mês), saldo
  da carteira, inadimplência e prazo médio das concessões, para pessoas físicas
  (quase tudo carro leve) e jurídicas (frotas, inclui caminhões).
- Banco Central, taxas de juros por instituição (atualizadas todo dia útil, em
  janelas móveis de 5 dias úteis): "Aquisição de veículos - Prefixado", pessoa
  física. Guarda a média simples e a mediana das instituições em cada janela.
- Trillia/B3 (SNG, gravames): quantidade de veículos financiados no mês, por
  autos leves, motos e pesados, lida da notícia mensal no site da B3.

  python credito_veiculos.py
"""

import json
import re
import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

ARQ = Path(__file__).parent / "alerts" / "credito_veiculos.json"
BRT = timezone(timedelta(hours=-3))
UA_API = {"User-Agent": "curl/8.5.0"}
UA_WEB = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36", "Accept-Language": "pt-BR,pt;q=0.9"}
SGS = {  # chave: (código, descrição)
    "taxa_pf": (20749, "Taxa média PF (% a.a.)"),
    "taxa_pj": (20728, "Taxa média PJ (% a.a.)"),
    "conc_pf": (20673, "Concessões PF (R$ milhões)"),
    "conc_pj": (20645, "Concessões PJ (R$ milhões)"),
    "saldo_pf": (20581, "Saldo PF (R$ milhões)"),
    "saldo_pj": (20553, "Saldo PJ (R$ milhões)"),
    "inad_pf": (21121, "Inadimplência PF (%)"),
    "inad_pj": (21096, "Inadimplência PJ (%)"),
    "prazo_pf": (20886, "Prazo médio das concessões PF (meses)"),
    "prazo_pj": (20864, "Prazo médio das concessões PJ (meses)"),
}
INICIO = "01/01/2023"
OLINDA = "https://olinda.bcb.gov.br/olinda/servico/taxaJuros/versao/v2/odata/TaxasJurosDiariaPorInicioPeriodo"
MODALIDADE = "Aquisição de veículos - Prefixado"
B3_LISTA = "https://www.b3.com.br/pt_br/noticias/"
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]


def _ler():
    try:
        return json.loads(ARQ.read_text(encoding="utf-8"))
    except Exception:
        return {}


def mensal():
    """{'meses': ['2023-01', ...], 'taxa_pf': [..], ...} alinhado por mês (None onde falta)."""
    series = {}
    for k, (cod, _) in SGS.items():
        r = requests.get(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{cod}/dados",
                         params={"formato": "json", "dataInicial": INICIO}, headers=UA_API, timeout=60)
        r.raise_for_status()
        series[k] = {f"{x['data'][6:10]}-{x['data'][3:5]}": float(x["valor"]) for x in r.json()}
    meses = sorted(set().union(*series.values()))
    out = {"meses": meses, "series": {k: SGS[k][1] for k in SGS}}
    for k, s in series.items():
        out[k] = [s.get(m) for m in meses]
    return out


def diaria(dias=200):
    """Média e mediana das taxas das instituições em cada janela (por data final)."""
    ini = (date.today() - timedelta(days=dias)).isoformat()
    # o Olinda não entende espaço como "+": a consulta vai montada à mão, com %20
    q = {"$format": "json", "$top": "50000", "$orderby": "InicioPeriodo desc",
         "$filter": f"Modalidade eq '{MODALIDADE}' and InicioPeriodo ge '{ini}'",
         "$select": "InicioPeriodo,FimPeriodo,InstituicaoFinanceira,TaxaJurosAoMes,TaxaJurosAoAno"}
    seguro = "',"
    url = OLINDA + "?" + "&".join(f"{k}={quote(v, safe=seguro)}" for k, v in q.items())
    r = requests.get(url, headers=UA_API, timeout=120)
    r.raise_for_status()
    if not r.json().get("value"):
        print("[AVISO] taxa diária: consulta sem linhas", url)
    jan = {}
    for x in r.json().get("value", []):
        jan.setdefault((x["InicioPeriodo"], x["FimPeriodo"]), []).append(x)
    out = []
    for (i, f), xs in sorted(jan.items(), key=lambda kv: kv[0][1]):
        am = [x["TaxaJurosAoMes"] for x in xs if x.get("TaxaJurosAoMes") is not None]
        aa = [x["TaxaJurosAoAno"] for x in xs if x.get("TaxaJurosAoAno") is not None]
        if len(am) < 5:
            continue
        out.append({"ini": i, "fim": f, "n": len(am),
                    "media_am": round(statistics.mean(am), 2), "mediana_am": round(statistics.median(am), 2),
                    "media_aa": round(statistics.mean(aa), 2), "mediana_aa": round(statistics.median(aa), 2)})
    # se houver duas janelas com o mesmo fim, fica a mais recente
    por_fim = {}
    for j in out:
        por_fim[j["fim"]] = j
    return [por_fim[k] for k in sorted(por_fim)]


def _mil(txt):
    """'478 mil' -> 478000 ; '683.928' -> 683928 ; '5,136 milhões' -> 5136000."""
    m = re.match(r"([\d.,]+)\s*(mil|milh)?", txt.strip())
    v = float(m.group(1).replace(".", "").replace(",", ".")) if "," in m.group(1) else float(m.group(1).replace(".", ""))
    return int(round(v * (1000 if m.group(2) == "mil" else 1_000_000 if m.group(2) == "milh" else 1)))


def b3_financiados():
    """Lê a notícia mensal de financiamentos (Trillia/B3). Devolve ('AAAA-MM', dados) ou None."""
    s = requests.Session()
    s.headers.update(UA_WEB)
    r = s.get(B3_LISTA, timeout=60)
    r.raise_for_status()
    links = []
    for href in re.findall(r'href="([^"]*noticias/[^"]+\.htm)"', r.text):
        if re.search(r"financ", href, re.I) and re.search(r"veicul|veícul", href, re.I):
            links.append(requests.compat.urljoin(B3_LISTA, href))
    for url in dict.fromkeys(links):
        t = BeautifulSoup(s.get(url, timeout=60).text, "html.parser").get_text(" ", strip=True)
        t = re.sub(r"\s+", " ", t)
        mt = re.search(r"[Ff]oram financiad[oa]s ([\d.]+) (?:unidades|veículos)", t)
        mm = re.search(r"\b(?:registrou|somou|teve) em (" + "|".join(MESES) + r")\b", t) or \
            re.search(r"\bem (" + "|".join(MESES) + r")\b", t)
        md = re.search(r"(\d{2})/(\d{2})/(\d{4})", t)
        if not (mt and mm and md):
            continue
        mes = MESES.index(mm.group(1)) + 1
        ano = int(md.group(3)) - (1 if mes > int(md.group(2)) else 0)
        d = {"total": _mil(mt.group(1)), "url": url, "publicado": f"{md.group(1)}/{md.group(2)}/{md.group(3)}"}
        for chave, rx in [("leves", r"autos leves,? (?:que )?somaram ([\d.,]+ mil)"),
                          ("motos", r"motos somaram ([\d.,]+ mil)"),
                          ("pesados", r"pesados totalizaram ([\d.,]+ mil)")]:
            m = re.search(rx, t)
            if m:
                d[chave] = _mil(m.group(1))
        m = re.search(r"pesados totalizaram[^.]*\.[^.]*?crescimento foi de ([\d,]+)%", t)
        if m:
            d["pesados_aa"] = float(m.group(1).replace(",", "."))
        m = re.search(r"comparação com \w+ de (\d{4}), o crescimento foi de ([\d,]+)%", t)
        if m:
            d["total_aa"] = float(m.group(2).replace(",", "."))
        return f"{ano}-{mes:02d}", d
    return None


B3_RELATORIOS = "https://www.b3.com.br/pt_br/market-data-e-indices/informacoes-para-mercado-de-financiamentos/veiculos/"
SEG_PAG = {"total": r"\|\s*TOTAL", "leves": r"LEVES", "motos": r"\|\s*MOTOS", "pesados": r"\|\s*PESADOS"}


def pdf_segmentos(conteudo, debug=False):
    """Lê um relatório mensal 'Mercado de Financiamentos de Veículos' (Trillia/B3).
    Em cada página de segmento há três quadros (mês, mês anterior e mesmo mês do ano
    anterior), cada um com total = usados + novos em mil unidades. Acha as trincas que
    fecham a soma e liga cada uma ao rótulo de mês mais próximo na horizontal.
    Devolve {'AAAA-MM': {'total': mil, 'leves': mil, ...}}."""
    import io
    import pdfplumber
    abrev = {m[:3]: i + 1 for i, m in enumerate(MESES)}
    out = {}
    with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
        for pg in pdf.pages[:12]:
            txt = pg.extract_text() or ""
            if "QUANTIDADE DE FINANCIAMENTO" not in txt or "ACUMULADO" in txt or "PARA O M" in txt or "EVOLU" in txt:
                continue
            seg = next((k for k, rx in SEG_PAG.items() if re.search(rx, txt)), None)
            if not seg:
                continue
            ws = pg.extract_words(x_tolerance=6, y_tolerance=3)
            labels, nums = [], []
            for w in ws:
                t = w["text"].replace(" ", "")
                xc = (w["x0"] + w["x1"]) / 2
                m = re.fullmatch(r"([a-z]{3})/(\d{2})", t)
                if m and m.group(1) in abrev:
                    labels.append((f"20{m.group(2)}-{abrev[m.group(1)]:02d}", xc, w["top"]))
                elif re.fullmatch(r"\d{1,4}", t) and w["x1"] - w["x0"] < 60:
                    nums.append((int(t), xc, w["top"]))
            trincas = []
            for a in nums:
                for b in nums:
                    for c in nums:
                        if a is b or a is c or b is c or a[0] < 10 or b[0] > a[0] or c[0] > a[0]:
                            continue
                        if abs(b[0] + c[0] - a[0]) <= 1 and abs(b[1] - c[1]) < 120 and abs(a[1] - b[1]) < 120:
                            trincas.append(a)
            trincas = list(dict.fromkeys(trincas))
            if debug:
                print("  pag", seg, "labels", labels, "trincas", trincas)
            for ym, x, _ in labels:
                if not trincas:
                    break
                best = min(trincas, key=lambda a: abs(a[1] - x))
                if abs(best[1] - x) < 90:
                    out.setdefault(ym, {})[seg] = best[0]
    return out


def sondar_b3(paginas=12):
    """Só para depuração: lista as notícias e relatórios (PDF) de financiamento de veículos
    da B3/Trillia e imprime os trechos com números por segmento."""
    s = requests.Session()
    s.headers.update(UA_WEB)
    seeds = [B3_RELATORIOS, B3_LISTA, "https://www.b3.com.br/pt_br/noticias/trillia.htm"]
    for tag in ("veiculos", "carros", "financiamento"):
        seeds += [f"https://borainvestir.b3.com.br/tudo-sobre/{tag}/"] + \
                 [f"https://borainvestir.b3.com.br/tudo-sobre/{tag}/page/{i}/" for i in range(2, paginas + 1)]
    arts, pdfs = {}, {}
    for u in seeds:
        try:
            r = s.get(u, timeout=40)
        except Exception as e:
            print("[seed erro]", u, e)
            continue
        print("[seed]", r.status_code, u)
        if r.status_code != 200:
            continue
        for href in re.findall(r'href="([^"]+)"', r.text):
            h = requests.compat.urljoin(u, href)
            if h.lower().endswith(".pdf") and re.search(r"financiamento", h, re.I):
                pdfs[h] = 1
            elif re.search(r"financ", h, re.I) and re.search(r"veicul|veícul|carros|motos", h, re.I) \
                    and re.search(r"/noticias/", h):
                arts[h] = 1
    import os
    for u in os.environ.get("B3_PDFS", "").split():
        pdfs[u] = 1
    arts = {}
    print("ARTIGOS", len(arts), "PDFS", len(pdfs))
    for u in list(arts)[:80]:
        try:
            html = s.get(u, timeout=40).text
        except Exception as e:
            print("[art erro]", u, e)
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            h = requests.compat.urljoin(u, a["href"])
            if h.lower().endswith(".pdf"):
                pdfs[h] = 1
        t = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
        tit = soup.title.get_text(strip=True) if soup.title else ""
        print("\n=== ART", u, "|", tit)
        for m in re.finditer(r"[^.]*(?:leves|motos|pesados|foram financiad|Publicado|\d{2}/\d{2}/\d{4})[^.]*\.", t):
            print("  >", m.group(0).strip()[:300])
    print("PDFS", len(pdfs))
    import io
    import pdfplumber
    for u in list(pdfs)[:60]:
        print("\n=== PDF", u)
        try:
            print("SEGMENTOS", pdf_segmentos(s.get(u, timeout=60).content, debug=True))
        except Exception as e:
            print("[pdf erro]", e)


def atualiza():
    d = _ler()
    erros = []
    try:
        d["mensal"] = mensal()
    except Exception as e:
        erros.append(f"SGS: {e}")
    try:
        nova = diaria()
        if nova:
            d["diaria"] = nova
    except Exception as e:
        erros.append(f"taxa diária: {e}")
    try:
        b = b3_financiados()
        if b:
            d.setdefault("b3", {})[b[0]] = b[1]
    except Exception as e:
        erros.append(f"B3: {e}")
    now = datetime.now(BRT)
    d.update(atualizado=now.strftime("%d/%m/%Y %H:%M"), atualizadoAt=now.isoformat(timespec="seconds"),
             fontes={"sgs": "https://www3.bcb.gov.br/sgspub/",
                     "diaria": "https://www.bcb.gov.br/estatisticas/txjuros",
                     "b3": B3_LISTA})
    ARQ.parent.mkdir(exist_ok=True)
    ARQ.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return erros


if __name__ == "__main__":
    import sys
    if "--sondar" in sys.argv:
        sondar_b3()
        sys.exit(0)
    for e in atualiza():
        print("[ERRO]", e)
    d = _ler()
    m = d.get("mensal", {})
    if m.get("meses"):
        i = len(m["meses"]) - 1
        print("Mensal", m["meses"][i], {k: m[k][i] for k in SGS})
    if d.get("diaria"):
        print("Diária", d["diaria"][-1])
    print("B3", d.get("b3"))
