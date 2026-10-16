"""
Radar de seminovos: preços anunciados nas vitrines de seminovos da Movida e da Localiza.

Toda segunda-feira (e quando pedido pelo botão do painel) lê todos os anúncios das duas vitrines (sem login, as mesmas buscas que o site
faz para quem navega) e guarda, por locadora e por categoria (hatch, sedã, SUV, picape, outros),
quantidade de carros, preço médio, preço mediano, km médio e ano-modelo médio.

Cada foto é comparada com a da semana anterior (semana a semana). A variação mês a mês sai de duas formas, como no resumo da FIPE:
  - preço médio da categoria no mês (média dos dias) contra o mês anterior, que mistura o efeito
    de preço com a mudança de mix (carros mais novos ou mais velhos à venda);
  - "mesma cesta": para cada modelo e ano-modelo com carros nos dois meses, a variação do preço
    mediano; a variação da categoria é a média geométrica dessas variações (pesada pelo número
    de carros), o que tira o efeito de mix.

Também compara o mesmo modelo e ano-modelo entre Movida e Localiza.

Fontes:
  Movida:   POST https://be-seminovos.movidacloud.com.br/elasticsearch/veiculos  (busca do site
            www.seminovosmovida.com.br, paginada por "from" e "size")
  Localiza: https://seminovos.localiza.com/carros?page=N  (dados da própria página, 23 por página)

Como as vitrines só mostram o preço de hoje, a visão mensal e em 12 meses desde já vem da Tabela
FIPE dos mesmos carros que a Movida anuncia (código FIPE e ano-modelo de cada anúncio, pesados pela
quantidade à venda), guardada em alerts/seminovos_fipe.json; e o preço pedido pela Movida frente à FIPE.

Saída: alerts/seminovos_hist.json (histórico diário por categoria e mensal por modelo/ano),
       alerts/seminovos_fipe.json (FIPE dos 13 últimos meses da cesta da Movida) e
       alerts/seminovos_resumo.json (resumo para o painel, entra em monitoramento.json).

Uso: python seminovos_radar.py [--so movida|localiza] [--max-paginas N]
"""
import argparse
import json
import math
import re
import statistics
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent
HIST = ROOT / "alerts" / "seminovos_hist.json"
RESUMO = ROOT / "alerts" / "seminovos_resumo.json"
BRT = timezone(timedelta(hours=-3))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
CATS = ["Hatch", "Sedã", "SUV", "Picape", "Outros"]
LOJAS = {"movida": "Movida", "localiza": "Localiza"}
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
MAX_DIAS = 400


def _ascii(s):
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().upper().strip()


def categoria(c):
    c = _ascii(c)
    if "HATCH" in c:
        return "Hatch"
    if "SEDAN" in c or "SEDA" in c:
        return "Sedã"
    if "SUV" in c:
        return "SUV"
    if "PICK" in c or "PICAPE" in c:
        return "Picape"
    return "Outros"


MARCA = {"GM": "CHEVROLET", "GENERAL MOTORS": "CHEVROLET", "VW": "VOLKSWAGEN", "CAOA CHERY": "CHERY", "MERCEDES BENZ": "MERCEDES-BENZ"}


def chave_modelo(marca, modelo, cat):
    """MARCA|PRIMEIRA PALAVRA DO MODELO|CATEGORIA, igual nas duas vitrines (ex.: CHEVROLET|ONIX|Sedã)."""
    m = MARCA.get(_ascii(marca), _ascii(marca))
    w = re.split(r"[\s\-]+", _ascii(modelo))
    w = (w[0] if w else "") or "?"
    if w in ("T", "C") and len(re.split(r"[\s\-]+", _ascii(modelo))) > 1:  # T-Cross, C4 Cactus
        w = _ascii(modelo).replace(" ", "").replace("-", "")[:8]
    return f"{m}|{w}|{cat}"


def nome_modelo(k):
    m, w, cat = k.split("|")
    return f"{m.title()} {w.title()} ({cat})"


# ---------------- coleta ----------------
def movida(max_paginas=None):
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*", "Accept-Language": "pt-BR,pt;q=0.9",
                      "Origin": "https://www.seminovosmovida.com.br", "Referer": "https://www.seminovosmovida.com.br/"})
    url = "https://be-seminovos.movidacloud.com.br/elasticsearch/veiculos"

    def varre(filtro):
        out, frm, total, pag = {}, 0, None, 0
        while True:
            body = {**filtro, "from": frm, "size": 200}
            for tent in range(4):
                try:
                    r = s.post(url, json=body, timeout=60)
                    r.raise_for_status()
                    j = r.json()
                    break
                except Exception as e:
                    print(f"::notice::Movida {filtro} from={frm}: {e}")
                    time.sleep(3 * (tent + 1))
            else:
                break
            t = j.get("total")
            total = t.get("value") if isinstance(t, dict) else t
            data = j.get("data") or []
            for x in data:
                out[x.get("id")] = x
            pag += 1
            if not data or len(data) < 200 or (max_paginas and pag >= max_paginas):
                break
            frm += 200
            if frm >= 10000:  # janela máxima do elasticsearch
                break
            time.sleep(0.3)
        return out, total

    carros, total = varre({})
    print(f"Movida: {len(carros)} de {total} na busca geral")
    if total and len(carros) < 0.98 * total and not max_paginas:
        for c in sorted({x.get("categoria") for x in carros.values() if x.get("categoria")}):
            sub, t = varre({"categorias": [c]})
            print(f"Movida {c}: {len(sub)} de {t}")
            carros.update(sub)
    lista = []
    for x in carros.values():
        p = x.get("preco")
        if not p or p < 5000:
            continue
        cat = categoria(x.get("categoria"))
        lista.append({"cat": cat, "modelo": chave_modelo(x.get("marca"), x.get("modelo"), cat), "ano": x.get("ano_modelo"),
                      "km": x.get("quilometragem"), "preco": float(p), "uf": x.get("uf"), "fipe": x.get("codigo_fipe"),
                      "comb": 3 if "DIESEL" in _ascii(x.get("combustivel")) else 1})
    return lista, total


def localiza(max_paginas=None):
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})
    base = "https://seminovos.localiza.com/carros"

    def pagina(n, build=None):
        for tent in range(4):
            try:
                if build:
                    r = s.get(f"https://seminovos.localiza.com/_next/data/{build}/carros.json", params={"page": n}, timeout=60,
                              headers={"Accept": "application/json"})
                    r.raise_for_status()
                    return r.json().get("pageProps", {}), build
                r = s.get(base, params={"page": n}, timeout=60, headers={"Accept": "text/html"})
                r.raise_for_status()
                m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
                d = json.loads(m.group(1))
                return d.get("props", {}).get("pageProps", {}), d.get("buildId")
            except Exception as e:
                print(f"::notice::Localiza página {n}: {e}")
                time.sleep(3 * (tent + 1))
                build = None if tent >= 1 else build  # se o JSON falhar, volta para a página HTML
        return None, build

    pp, build = pagina(1)
    if not pp:
        return [], None
    meta = pp.get("_metadados") or {}
    total, npag = meta.get("_total"), meta.get("_totalPaginas") or 1
    carros = {x["id"]: x for x in pp.get("products") or []}
    if max_paginas:
        npag = min(npag, max_paginas)
    falhas = 0
    for n in range(2, npag + 1):
        q, build = pagina(n, build)
        if q is None:
            falhas += 1
            if falhas > 20:
                break
            continue
        for x in q.get("products") or []:
            carros[x["id"]] = x
        time.sleep(0.15)
    print(f"Localiza: {len(carros)} de {total} ({npag} páginas, {falhas} falhas)")
    lista = []
    for x in carros.values():
        p = x.get("preco")
        if not p or p < 5000:
            continue
        cat = categoria(x.get("categoriaDescricao"))
        lista.append({"cat": cat, "modelo": chave_modelo(x.get("marcaDescricao"), x.get("modeloFamiliaDescricao"), cat),
                      "ano": x.get("anoModelo"), "km": x.get("odometro"), "preco": float(p), "uf": x.get("siglaEstado")})
    return lista, total


# ---------------- FIPE dos carros à venda na Movida ----------------
FIPE_CACHE = ROOT / "alerts" / "seminovos_fipe.json"
FIPE_ITENS = 120      # células (código FIPE + ano-modelo) mais anunciadas que entram na cesta
FIPE_MESES = 13       # meses de referência (12 variações mensais e a variação em 12 meses)
FIPE_PRAZO = 22 * 60  # segundos de consultas por rodada; o que faltar vem nas próximas


def fipe_atualiza(lista):
    """Guarda, para os modelos/anos mais anunciados pela Movida, o preço FIPE dos últimos 13 meses."""
    from fipe_mensal import Fipe, parse_mes, parse_valor, TIPOS

    class F(Fipe):
        def preco_codigo(self, ref, fipe, ano, comb):
            js = self._post("ConsultarValorComTodosParametros", {
                "codigoTabelaReferencia": ref, "codigoTipoVeiculo": 1, "anoModelo": ano, "codigoTipoCombustivel": comb,
                "tipoVeiculo": TIPOS[1], "modeloCodigoExternoFipe": fipe, "tipoConsulta": "codigo"})
            if js is not None:
                if js.get("Valor"):
                    return parse_valor(js["Valor"])
                if js.get("erro") == "nadaencontrado":
                    return 0
            js = self._get_reserva(f"cars/{fipe}/years/{ano}-{comb}", {"reference": ref})
            if not js:  # sem resposta, ou o espelho não achou: tenta de novo na próxima rodada
                raise RuntimeError("sem resposta")
            return parse_valor(js.get("price")) if js.get("price") else 0

    c = json.loads(FIPE_CACHE.read_text(encoding="utf-8")) if FIPE_CACHE.exists() else {"refs": {}, "precos": {}, "itens": {}}
    cel = {}
    for x in lista:
        if x.get("fipe") and x.get("ano"):
            a = cel.setdefault(f"{x['fipe']}|{x['ano']}|{x['comb']}", {"cat": x["cat"], "modelo": x["modelo"], "n": 0, "soma": 0})
            a["n"] += 1; a["soma"] += x["preco"]
    top = sorted(cel, key=lambda k: -cel[k]["n"])[:FIPE_ITENS]
    c["itens"] = {k: {"cat": cel[k]["cat"], "modelo": cel[k]["modelo"], "n": cel[k]["n"], "preco_movida": round(cel[k]["soma"] / cel[k]["n"])}
                  for k in top}
    fp = F()
    refs = fp.referencias()[:FIPE_MESES]
    if not refs:
        print("::warning::FIPE: sem tabelas de referência")
        return c
    for cod, lab in refs:
        ym = parse_mes(lab)
        if ym:
            c["refs"][f"{ym[0]}-{ym[1]:02d}"] = cod
    meses = sorted(c["refs"], reverse=True)[:FIPE_MESES]
    t0, feitos, falhas = time.monotonic(), 0, 0
    for k in top:
        fipe, ano, comb = k.split("|")
        pr = c["precos"].setdefault(k, {})
        for m in meses:
            if m in pr:
                continue
            if time.monotonic() - t0 > FIPE_PRAZO:
                break
            if not fp.disponivel():
                fp.esperar(time.monotonic() + 120)
            try:
                v = fp.preco_codigo(c["refs"][m], fipe, int(ano), int(comb))
            except RuntimeError:
                falhas += 1
                continue
            if v == 0 and comb == "1":  # carro a diesel ou elétrico cadastrado com outro combustível
                for alt in (3, 4):
                    try:
                        v = fp.preco_codigo(c["refs"][m], fipe, int(ano), alt) or 0
                    except RuntimeError:
                        v = 0
                    if v:
                        break
            pr[m] = v or None
            feitos += 1
    # descarta meses velhos e itens que saíram da vitrine há tempo
    for k in list(c["precos"]):
        c["precos"][k] = {m: v for m, v in c["precos"][k].items() if m in meses}
        if k not in c["itens"] and not c["precos"][k]:
            del c["precos"][k]
    c["refs"] = {m: c["refs"][m] for m in meses}
    c["atualizado"] = datetime.now(BRT).isoformat(timespec="seconds")
    FIPE_CACHE.write_text(json.dumps(c, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    falta = sum(1 for k in top for m in meses if m not in c["precos"].get(k, {}))
    print(f"FIPE: {feitos} consultas novas, {falhas} sem resposta, {falta} pendentes para as próximas rodadas")
    return c


def fipe_resumo(c):
    """Variação mensal e em 12 meses da FIPE da cesta de carros da Movida (pesos = carros anunciados)."""
    meses = sorted(c.get("refs", {}))
    if len(meses) < 2:
        return None
    itens, pr = c["itens"], c["precos"]

    def var(m0, m1, cat=None, mk=None):
        sw = sl = 0
        for k, it in itens.items():
            if (cat and cat != "Total" and it["cat"] != cat) or (mk and it["modelo"] != mk):
                continue
            a, b = pr.get(k, {}).get(m0), pr.get(k, {}).get(m1)
            if a and b:
                sw += it["n"]; sl += it["n"] * math.log(b / a)
        return round((math.exp(sl / sw) - 1) * 100, 2) if sw else None

    cats = [x for x in CATS + ["Total"] if x == "Total" or any(it["cat"] == x for it in itens.values())]
    mensal = [{"mes": m, "curto": curto(m), **{k: var(meses[i - 1], m, k) for k in cats}} for i, m in enumerate(meses) if i]
    ult = meses[-1]
    dez = f"{int(ult[:4]) - 1}-12"
    out = {"meses": len(meses), "ultimo": ult, "ultimo_curto": curto(ult), "mensal": mensal, "cats": cats,
           "doze": {k: var(meses[0], ult, k) for k in cats} if len(meses) >= 13 else None,
           "doze_de": curto(meses[0]),
           "ano": {k: var(dez, ult, k) for k in cats} if dez in meses else None,
           "cobertura": {"itens": sum(1 for k in itens if pr.get(k, {}).get(ult)), "de": len(itens),
                         "carros": sum(it["n"] for k, it in itens.items() if pr.get(k, {}).get(ult))}}
    # preço pedido pela Movida frente à FIPE do mês (mesmo código e ano-modelo)
    rel = {}
    for k, it in itens.items():
        f = pr.get(k, {}).get(ult)
        if f:
            for g in (it["cat"], "Total"):
                a = rel.setdefault(g, [0, 0]); a[0] += it["n"]; a[1] += it["n"] * math.log(it["preco_movida"] / f)
    out["vs_fipe"] = {g: round((math.exp(s / n) - 1) * 100, 2) for g, (n, s) in rel.items() if n}
    mods = {}
    for it in itens.values():
        mods[it["modelo"]] = mods.get(it["modelo"], 0) + it["n"]
    out["modelos"] = [{"modelo": nome_modelo(mk), "n": n, "mes": var(meses[-2], ult, mk=mk),
                       "doze": var(meses[0], ult, mk=mk) if len(meses) >= 13 else None,
                       "ano": var(dez, ult, mk=mk) if dez in meses else None}
                      for mk, n in sorted(mods.items(), key=lambda x: -x[1])[:20]]
    return out


# ---------------- agregação ----------------
def resumo_cat(lst):
    pr = [x["preco"] for x in lst]
    km = [x["km"] for x in lst if x.get("km") is not None]
    an = [x["ano"] for x in lst if x.get("ano")]
    return {"n": len(lst), "media": round(statistics.fmean(pr)), "mediana": round(statistics.median(pr)),
            "km": round(statistics.fmean(km)) if km else None, "ano": round(statistics.fmean(an), 1) if an else None}


def foto(lista):
    cats = {c: resumo_cat([x for x in lista if x["cat"] == c]) for c in CATS if any(x["cat"] == c for x in lista)}
    cats["Total"] = resumo_cat(lista)
    cel = {}
    for x in lista:
        if x.get("ano"):
            cel.setdefault(f"{x['modelo']}|{x['ano']}", []).append(x["preco"])
    cells = {k: [len(v), round(statistics.median(v))] for k, v in cel.items()}
    return {"cats": cats, "cells": cells}


def acumula_mes(mes_doc, loja, f):
    """mensal[loja]: soma dos dias (preço médio e mediano por categoria; mediana e n por célula)."""
    m = mes_doc.setdefault(loja, {"dias": 0, "cats": {}, "cells": {}})
    m["dias"] += 1
    for c, v in f["cats"].items():
        a = m["cats"].setdefault(c, {"dias": 0, "n": 0, "media": 0, "mediana": 0, "km": 0, "ano": 0})
        a["dias"] += 1
        for k in ("n", "media", "mediana", "km", "ano"):
            a[k] += v.get(k) or 0
    for k, (n, med) in f["cells"].items():
        a = m["cells"].setdefault(k, [0, 0, 0])  # dias, soma n, soma mediana
        a[0] += 1; a[1] += n; a[2] += med


def media_mes(m):
    cats = {c: {k: (a[k] / a["dias"]) for k in ("n", "media", "mediana", "km", "ano")} for c, a in m["cats"].items() if a["dias"]}
    cells = {k: (a[1] / a[0], a[2] / a[0]) for k, a in m["cells"].items() if a[0]}
    return cats, cells


def cesta(cells_a, cells_b, cat=None, min_n=2):
    """Média geométrica (pesada por quantidade) da variação do preço mediano por modelo/ano presente nos dois meses."""
    sw = sl = 0
    for k, (n1, p1) in cells_b.items():
        if cat and k.split("|")[2] != cat:
            continue
        if k in cells_a and p1 > 0 and cells_a[k][1] > 0 and n1 >= min_n and cells_a[k][0] >= min_n:
            w = min(n1, cells_a[k][0])
            sw += w; sl += w * math.log(p1 / cells_a[k][1])
    return (round((math.exp(sl / sw) - 1) * 100, 2), round(sw)) if sw else (None, 0)


def pct(a, b):
    return round((b / a - 1) * 100, 2) if a and b else None


def curto(mes):
    y, m = mes.split("-")
    return f"{MESES[int(m) - 1]}/{y[2:]}"


def monta_resumo(h, hoje):
    meses = sorted(h["mensal"])
    out = {"gerado_em": datetime.now(BRT).isoformat(timespec="seconds"), "dia": hoje, "lojas": {}, "mensal": [], "modelos": [],
           "comparacao": [], "semanal": {}}
    for loja in LOJAS:
        d = h["dias"].get(hoje, {}).get(loja) or next((h["dias"][x][loja] for x in sorted(h["dias"], reverse=True) if loja in h["dias"][x]), None)
        if d:
            out["lojas"][loja] = {"cats": d["cats"], "total_site": d.get("total_site"), "dia": d.get("dia", hoje)}
        out["semanal"] = out.get("semanal", {})
        out["semanal"][loja] = [{"dia": x, "cats": {c: {"media": v.get("media"), "n": v.get("n"), **(h["dias"][x][loja].get("sem", {}).get(c) or {})}
                                                    for c, v in h["dias"][x][loja]["cats"].items()}}
                                for x in sorted(h["dias"])[-27:] if loja in h["dias"][x]]
    medias = {mes: {loja: media_mes(h["mensal"][mes][loja]) for loja in h["mensal"][mes]} for mes in meses}
    for i, mes in enumerate(meses):
        linha = {"mes": mes, "curto": curto(mes), "lojas": {}}
        for loja, (cats, cells) in medias[mes].items():
            ant = medias.get(meses[i - 1], {}).get(loja) if i else None
            dl = {}
            for c, v in cats.items():
                dl[c] = {"media": round(v["media"]), "mediana": round(v["mediana"]), "n": round(v["n"]), "km": round(v["km"]) if v["km"] else None,
                         "ano": round(v["ano"], 1) if v["ano"] else None, "dias": h["mensal"][mes][loja]["cats"][c]["dias"]}
                if ant and c in ant[0]:
                    dl[c]["var"] = pct(ant[0][c]["media"], v["media"])
                    dl[c]["var_cesta"], dl[c]["cesta_n"] = cesta(ant[1], cells, None if c == "Total" else c)
                for nome, ref in (("var_12m", f"{int(mes[:4]) - 1}{mes[4:]}"), ("var_ano", f"{int(mes[:4]) - 1}-12")):
                    base = medias.get(ref, {}).get(loja)
                    if base and ref != mes and c in base[0]:
                        dl[c][nome] = cesta(base[1], cells, None if c == "Total" else c)[0]
            linha["lojas"][loja] = dl
        out["mensal"].append(linha)
    if meses:
        cur = medias[meses[-1]]
        prev = medias.get(meses[-2]) if len(meses) > 1 else None
        # modelos mais anunciados, com preço médio por locadora e variação no mês (mesmo modelo/ano)
        mods = {}
        for loja, (cats, cells) in cur.items():
            for k, (n, p) in cells.items():
                mk = k.rsplit("|", 1)[0]
                a = mods.setdefault(mk, {}).setdefault(loja, [0, 0])
                a[0] += n; a[1] += n * p
        top = sorted(mods, key=lambda mk: -sum(v[0] for v in mods[mk].values()))[:30]
        for mk in top:
            row = {"modelo": nome_modelo(mk), "cat": mk.split("|")[2]}
            for loja, (n, s) in mods[mk].items():
                row[loja] = {"n": round(n), "preco": round(s / n) if n else None}
                if prev and loja in prev:
                    sub_a = {k: v for k, v in prev[loja][1].items() if k.startswith(mk + "|")}
                    sub_b = {k: v for k, v in cur[loja][1].items() if k.startswith(mk + "|")}
                    row[loja]["var"] = cesta(sub_a, sub_b, min_n=1)[0]
            out["modelos"].append(row)
        # mesmo modelo e ano-modelo nas duas locadoras: quanto a Movida está acima/abaixo da Localiza
        if "movida" in cur and "localiza" in cur:
            cm, cl = cur["movida"][1], cur["localiza"][1]
            for c in CATS + ["Total"]:
                sw = sl = 0
                for k, (n1, p1) in cm.items():
                    if (c == "Total" or k.split("|")[2] == c) and k in cl and n1 >= 2 and cl[k][0] >= 2:
                        w = min(n1, cl[k][0]); sw += w; sl += w * math.log(p1 / cl[k][1])
                if sw:
                    out["comparacao"].append({"cat": c, "dif": round((math.exp(sl / sw) - 1) * 100, 2), "carros": round(sw)})
    # frase de resumo
    ult = out["mensal"][-1] if out["mensal"] else None
    partes = []
    if ult:
        for loja, nome in LOJAS.items():
            t = ult["lojas"].get(loja, {}).get("Total")
            if t:
                mil = lambda v: f"{v:,}".replace(",", ".")
                s = f"{nome}: {mil(t['n'])} carros anunciados, preço médio R$ {mil(t['media'])}"
                if t.get("var_cesta") is not None:
                    s += f", {'+' if t['var_cesta'] > 0 else ''}{str(t['var_cesta']).replace('.', ',')}% no mês na mesma cesta de modelos"
                partes.append(s)
    out["resumo"] = ". ".join(partes) + "." if partes else ""
    if len(meses) < 2:
        out["aviso"] = (f"Coleta semanal (segundas) desde {curto(meses[0]) if meses else 'hoje'}; a variação mês a mês aparece quando houver dois meses "
                        "de dados (o site das locadoras não mostra preços antigos).")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--so", choices=list(LOJAS))
    ap.add_argument("--max-paginas", type=int)
    ap.add_argument("--sem-fipe", action="store_true", help="não consulta a FIPE (usa o que já está guardado)")
    a = ap.parse_args()
    h = json.loads(HIST.read_text(encoding="utf-8")) if HIST.exists() else {"dias": {}, "mensal": {}}
    hoje = datetime.now(BRT).date().isoformat()
    mes = hoje[:7]
    ok = 0
    lista_movida = None
    for loja, fn in (("movida", movida), ("localiza", localiza)):
        if a.so and a.so != loja:
            continue
        try:
            lista, total = fn(a.max_paginas)
        except Exception as e:
            print(f"::warning::{LOJAS[loja]}: falhou a coleta ({e})")
            continue
        if not lista or (total and len(lista) < 0.8 * total and not a.max_paginas):
            print(f"::warning::{LOJAS[loja]}: coleta incompleta ({len(lista)} de {total}); dia não gravado")
            continue
        f = foto(lista)
        if loja == "movida":
            lista_movida = lista
        ja = h["dias"].get(hoje, {}).get(loja)
        if ja and not a.max_paginas:  # já coletado hoje: troca a foto do dia sem contar o dia duas vezes no mês
            m = h["mensal"].get(mes, {}).get(loja)
            if m:
                m["dias"] -= 1
                for c, v in ja["cats"].items():
                    x = m["cats"].get(c)
                    if x:
                        x["dias"] -= 1
                        for k in ("n", "media", "mediana", "km", "ano"):
                            x[k] -= v.get(k) or 0
                for k, (n, med) in ja.get("cells", {}).items():
                    x = m["cells"].get(k)
                    if x:
                        x[0] -= 1; x[1] -= n; x[2] -= med
        if a.max_paginas:
            print(json.dumps(f["cats"], ensure_ascii=False))
            continue
        # variação contra a foto anterior (rodada semanal: a da segunda-feira passada), ainda com as células por modelo/ano
        ant = next((h["dias"][d][loja] for d in sorted(h["dias"], reverse=True)
                    if d <= (datetime.fromisoformat(hoje) - timedelta(days=5)).date().isoformat() and loja in h["dias"][d]
                    and h["dias"][d][loja].get("cells")), None)
        sem = None
        if ant:
            sem = {c: {"var": pct(ant["cats"].get(c, {}).get("media"), v["media"]),
                       "var_cesta": cesta({k: tuple(x) for k, x in ant["cells"].items()}, {k: tuple(x) for k, x in f["cells"].items()},
                                          None if c == "Total" else c)[0]} for c, v in f["cats"].items()}
        h["dias"].setdefault(hoje, {})[loja] = {"cats": f["cats"], "cells": f["cells"], "total_site": total, **({"sem": sem} if sem else {})}
        acumula_mes(h["mensal"].setdefault(mes, {}), loja, f)
        ok += 1
        print(f"{LOJAS[loja]}: {len(lista)} carros, preço médio R$ {f['cats']['Total']['media']:,}")
    if a.max_paginas:
        return
    # só a foto por categoria fica no histórico; as células por modelo/ano ficam no mensal e nas fotos dos últimos 10 dias
    lim = (datetime.fromisoformat(hoje) - timedelta(days=10)).date().isoformat()
    for d in sorted(h["dias"]):
        if d < lim:
            for v in h["dias"][d].values():
                v.pop("cells", None)
    for d in sorted(h["dias"])[:-MAX_DIAS]:
        del h["dias"][d]
    HIST.parent.mkdir(exist_ok=True)
    HIST.write_text(json.dumps(h, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    res = monta_resumo(h, hoje)
    try:
        c = fipe_atualiza(lista_movida) if lista_movida and not a.sem_fipe else (
            json.loads(FIPE_CACHE.read_text(encoding="utf-8")) if FIPE_CACHE.exists() else None)
        res["fipe"] = fipe_resumo(c) if c else None
    except Exception as e:
        print(f"::warning::FIPE da cesta da Movida: {e}")
    RESUMO.write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
