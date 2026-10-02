"""
Resumo mensal da Tabela FIPE por segmento (hatch, sedã, SUV, picape, caminhão, moto).

A FIPE não classifica os veículos por carroceria, então o resumo usa uma cesta fixa
de modelos representativos de cada segmento (CESTA abaixo). Para cada modelo são
escolhidas até 2 versões vigentes e 2 anos-modelo (o mais novo usado e ~3 anos
antes). A variação do segmento no mês é a média geométrica das variações de preço
dos itens que têm preço nos dois meses; "Leves" junta hatch, sedã, SUV e picape.

Roda pelo workflow "Resumo FIPE mensal" nos dias 1 a 10 às 8h30 e às 19h: quando a
FIPE publica uma tabela nova (mês de referência ainda não enviado), busca os preços
e envia o e-mail. A cesta e o histórico ficam em alerts/fipe_*.json, então depois
da primeira carga cada mês custa poucas consultas.

Fonte: API pública do site veiculos.fipe.org.br (com o espelho parallelum.com.br
como reserva, que usa os mesmos códigos de marca e modelo).

Uso:
  python fipe_mensal.py                 # envia só se houver tabela nova
  python fipe_mensal.py --force --teste # envia agora, com [Teste] no assunto
  python fipe_mensal.py --dry-run       # não envia; salva alerts/fipe_preview.html
  python fipe_mensal.py --demo --dry-run  # dados simulados, sem internet
"""

import argparse
import json
import math
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from alerta_acoes import send_email
from email_layout import (DOWN, INK, MUTED, UP, color_for, data_table, esc, page, row,
                          section_title)

BRT = timezone(timedelta(hours=-3))
ROOT = Path(__file__).parent
OUT_DIR = ROOT / "alerts"
CESTA_FILE = OUT_DIR / "fipe_cesta.json"
HIST_FILE = OUT_DIR / "fipe_historico.json"
STATE_FILE = OUT_DIR / "fipe_state.json"
RESUMO_FILE = OUT_DIR / "fipe_resumo.json"
PREVIEW_FILE = OUT_DIR / "fipe_preview.html"

MESES_HIST = 13          # meses de referência guardados (12 variações mês a mês)
VERSOES_POR_MODELO = 2
DELAY = 0.5              # pausa entre consultas à FIPE (s)

# tipo FIPE: 1 = carro (inclui picapes e SUVs), 2 = moto, 3 = caminhão
TIPOS = {1: "carro", 2: "moto", 3: "caminhao"}
TIPOS_PARALLELUM = {1: "cars", 2: "motorcycles", 3: "trucks"}

SEGMENTOS = ["Hatch", "Sedã", "SUV", "Picape", "Caminhão", "Moto"]
LEVES = ["Hatch", "Sedã", "SUV", "Picape"]

# (segmento, tipo, regex da marca, regex do modelo, regex de exclusão, nome curto)
CESTA = [
    ("Hatch", 1, r"chevrolet", r"^onix\b", r"plus|sedan|joy|activ", "Chevrolet Onix"),
    ("Hatch", 1, r"hyundai", r"^hb20\b", r"hb20s|hb20x|sedan", "Hyundai HB20"),
    ("Hatch", 1, r"volkswagen", r"^polo\b", r"sedan|track|gti|classic", "VW Polo"),
    ("Hatch", 1, r"^fiat", r"^argo\b", r"", "Fiat Argo"),
    ("Hatch", 1, r"^fiat", r"^mobi\b", r"", "Fiat Mobi"),
    ("Hatch", 1, r"renault", r"^kwid\b", r"e-tech|el[eé]tric", "Renault Kwid"),
    ("Sedã", 1, r"toyota", r"^corolla\b", r"cross|fielder|gr", "Toyota Corolla"),
    ("Sedã", 1, r"honda", r"^civic\b", r"type|si\b|hatch", "Honda Civic"),
    ("Sedã", 1, r"chevrolet", r"^onix\s+(plus|sedan)", r"", "Chevrolet Onix Plus"),
    ("Sedã", 1, r"volkswagen", r"^virtus\b", r"gts", "VW Virtus"),
    ("Sedã", 1, r"hyundai", r"^hb20s\b", r"", "Hyundai HB20S"),
    ("Sedã", 1, r"nissan", r"^(new\s+)?versa\b", r"", "Nissan Versa"),
    ("SUV", 1, r"jeep", r"^compass\b", r"4xe|trailhawk", "Jeep Compass"),
    ("SUV", 1, r"jeep", r"^renegade\b", r"", "Jeep Renegade"),
    ("SUV", 1, r"volkswagen", r"^t-?cross\b", r"", "VW T-Cross"),
    ("SUV", 1, r"hyundai", r"^creta\b", r"", "Hyundai Creta"),
    ("SUV", 1, r"honda", r"^hr-?v\b", r"", "Honda HR-V"),
    ("SUV", 1, r"toyota", r"^corolla\s+cross\b", r"gr", "Toyota Corolla Cross"),
    ("SUV", 1, r"chevrolet", r"^tracker\b", r"", "Chevrolet Tracker"),
    ("SUV", 1, r"volkswagen", r"^nivus\b", r"", "VW Nivus"),
    ("Picape", 1, r"^fiat", r"^strada\b", r"", "Fiat Strada"),
    ("Picape", 1, r"^fiat", r"^toro\b", r"", "Fiat Toro"),
    ("Picape", 1, r"toyota", r"^hilux\b", r"sw4|gr", "Toyota Hilux"),
    ("Picape", 1, r"chevrolet", r"^s10\b", r"blazer|trailblazer", "Chevrolet S10"),
    ("Picape", 1, r"^ford", r"^ranger\b", r"raptor", "Ford Ranger"),
    ("Picape", 1, r"volkswagen", r"^saveiro\b", r"", "VW Saveiro"),
    ("Picape", 1, r"volkswagen", r"^amarok\b", r"", "VW Amarok"),
    ("Picape", 1, r"mitsubishi", r"^l200\b", r"", "Mitsubishi L200"),
    ("Caminhão", 3, r"volvo", r"^fh\b", r"", "Volvo FH"),
    ("Caminhão", 3, r"volvo", r"^vm\b", r"", "Volvo VM"),
    ("Caminhão", 3, r"scania", r"^r[\s-]?\d{3}", r"", "Scania R"),
    ("Caminhão", 3, r"mercedes", r"^actros\b", r"", "Mercedes-Benz Actros"),
    ("Caminhão", 3, r"mercedes", r"^atego\b", r"", "Mercedes-Benz Atego"),
    ("Caminhão", 3, r"mercedes", r"^accelo\b", r"", "Mercedes-Benz Accelo"),
    ("Caminhão", 3, r"volkswagen", r"^(constellation\b|2[4-6]\.\d{3})", r"", "VW Constellation"),
    ("Caminhão", 3, r"volkswagen", r"^(delivery\b|(9|11)\.1[5-9]0)", r"", "VW Delivery"),
    ("Caminhão", 3, r"\bdaf\b", r"^xf\b", r"", "DAF XF"),
    ("Moto", 2, r"honda", r"^cg\s*160\b", r"", "Honda CG 160"),
    ("Moto", 2, r"honda", r"^biz\b", r"", "Honda Biz"),
    ("Moto", 2, r"honda", r"^nxr\s*160\b|^bros\b", r"", "Honda Bros 160"),
    ("Moto", 2, r"honda", r"^pcx\b", r"", "Honda PCX"),
    ("Moto", 2, r"honda", r"^cb\s*300", r"", "Honda CB 300F"),
    ("Moto", 2, r"yamaha", r"^(fazer\s*)?fz\s*25\b|^fazer\s*250\b", r"", "Yamaha Fazer 250"),
    ("Moto", 2, r"yamaha", r"^factor\b", r"", "Yamaha Factor 150"),
    ("Moto", 2, r"yamaha", r"^xtz\s*150\b|crosser", r"", "Yamaha Crosser 150"),
]

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Referer": "https://veiculos.fipe.org.br/",
    "Origin": "https://veiculos.fipe.org.br",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}

MESES = {"janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
         "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
MES_CURTO = ["", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


# ---------------------------------------------------------------- utilidades
def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def parse_valor(s):
    """'R$ 123.456,00' -> 123456.0"""
    s = re.sub(r"[^\d,]", "", s or "")
    return float(s.replace(",", ".")) if s else None


def parse_mes(label):
    """'outubro/2026 ' ou 'outubro de 2026' -> (2026, 10)"""
    m = re.search(r"([a-zç]+)\D+(\d{4})", (label or "").lower())
    if not m or m.group(1) not in MESES:
        return None
    return int(m.group(2)), MESES[m.group(1)]


def mes_nome(label):
    ym = parse_mes(label)
    if not ym:
        return label.strip()
    nome = [k for k, v in MESES.items() if v == ym[1] and k != "marco"][0]
    return f"{nome}/{ym[0]}"


def mes_curto(label):
    ym = parse_mes(label)
    return f"{MES_CURTO[ym[1]]}/{str(ym[0])[2:]}" if ym else label.strip()


def brl(v):
    return "–" if v is None else "R$ " + f"{v:,.0f}".replace(",", ".")


def pct(v, casas=1):
    if v is None:
        return "–"
    s = f"{v:+.{casas}f}%".replace(".", ",")
    return s.replace("+0,0%", "0,0%").replace("-0,0%", "0,0%")


def pct_html(v, casas=1, bold=False):
    w = "font-weight:700;" if bold else ""
    return f'<span style="{w}color:{color_for(v)}">{esc(pct(v, casas))}</span>'


# ---------------------------------------------------------------- cliente FIPE
class Fipe:
    """Cliente da FIPE. O site oficial bloqueia (HTTP 403) depois de algumas centenas de
    consultas seguidas; nesse caso o cliente faz uma pausa no site e, enquanto isso, usa o
    espelho parallelum (mesmos códigos de marca/modelo). Para o espelho, um token gratuito
    de fipe.online no secret FIPE_TOKEN aumenta o limite diário."""
    BASE = "https://veiculos.fipe.org.br/api/veiculos/"
    RESERVA = "https://fipe.parallelum.com.br/api/v2/"

    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update(HEADERS)
        self.r = requests.Session()
        self.r.headers["User-Agent"] = HEADERS["User-Agent"]
        if os.environ.get("FIPE_TOKEN"):
            self.r.headers["X-Subscription-Token"] = os.environ["FIPE_TOKEN"]
        self.calls = 0
        self.reserva_calls = 0
        self.pausa_ate = 0.0      # time.monotonic() até quando o site oficial fica de lado
        self.pausa = 120          # duração da próxima pausa (s), dobra a cada bloqueio
        self.reserva_ate = 0.0    # idem para o espelho (limite diário / 429)

    def _post(self, endpoint, data):
        if time.monotonic() < self.pausa_ate:
            return None
        for i in range(2):
            time.sleep(DELAY)
            self.calls += 1
            try:
                r = self.s.post(self.BASE + endpoint, data=data, timeout=20)
                if r.status_code == 200:
                    self.pausa = 120
                    return r.json()
                if r.status_code in (403, 429):
                    print(f"[AVISO] FIPE bloqueou ({r.status_code}); pausa de {self.pausa}s no site oficial "
                          f"(usando o espelho enquanto isso). Consultas até aqui: {self.calls}", flush=True)
                    self.pausa_ate = time.monotonic() + self.pausa
                    self.pausa = min(self.pausa * 2, 1800)
                    return None
                print(f"[AVISO] FIPE {endpoint} HTTP {r.status_code}", flush=True)
            except (requests.RequestException, ValueError) as exc:
                print(f"[AVISO] FIPE {endpoint}: {exc}", flush=True)
            time.sleep(3)
        return None

    def _get_reserva(self, path, params=None):
        """Retorna o JSON; {} se o espelho não tem o item (404); None se não respondeu."""
        if time.monotonic() < self.reserva_ate:
            return None
        for i in range(2):
            time.sleep(DELAY)
            self.reserva_calls += 1
            try:
                r = self.r.get(self.RESERVA + path, params=params, timeout=30)
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 404:
                    return {}
                print(f"[AVISO] parallelum {path} HTTP {r.status_code}: {r.text[:120]}", flush=True)
                if r.status_code in (401, 403, 429):
                    self.reserva_ate = time.monotonic() + 600
                    return None
            except (requests.RequestException, ValueError) as exc:
                print(f"[AVISO] parallelum {path}: {exc}", flush=True)
            time.sleep(3)
        return None

    def disponivel(self):
        agora = time.monotonic()
        return agora >= self.pausa_ate or agora >= self.reserva_ate

    def esperar(self, prazo):
        """As duas fontes estão bloqueadas: espera a primeira liberar (sem passar do prazo)."""
        t = min(self.pausa_ate, self.reserva_ate, prazo) - time.monotonic()
        if t > 0:
            print(f"[INFO] Fontes bloqueadas; aguardando {t:.0f}s", flush=True)
            time.sleep(t)

    def referencias(self):
        """[(codigo, 'outubro/2026'), ...] do mais novo para o mais antigo."""
        js = self._post("ConsultarTabelaDeReferencia", {})
        if js:
            refs = [(int(x["Codigo"]), x["Mes"].strip()) for x in js]
        else:
            js = self._get_reserva("references") or []
            refs = [(int(x["code"]), mes_nome(x["month"])) for x in js]
        return sorted(refs, reverse=True)

    def marcas(self, ref, tipo):
        js = self._post("ConsultarMarcas", {"codigoTabelaReferencia": ref, "codigoTipoVeiculo": tipo})
        if js:
            return [(str(x["Value"]), x["Label"]) for x in js]
        js = self._get_reserva(f"{TIPOS_PARALLELUM[tipo]}/brands", {"reference": ref}) or []
        return [(str(x["code"]), x["name"]) for x in js]

    def modelos(self, ref, tipo, marca):
        js = self._post("ConsultarModelos", {"codigoTabelaReferencia": ref, "codigoTipoVeiculo": tipo,
                                             "codigoMarca": marca})
        if js and js.get("Modelos"):
            return [(str(x["Value"]), x["Label"]) for x in js["Modelos"]]
        js = self._get_reserva(f"{TIPOS_PARALLELUM[tipo]}/brands/{marca}/models", {"reference": ref}) or []
        return [(str(x["code"]), x["name"]) for x in js]

    def anos(self, ref, tipo, marca, modelo):
        js = self._post("ConsultarAnoModelo", {"codigoTabelaReferencia": ref, "codigoTipoVeiculo": tipo,
                                               "codigoMarca": marca, "codigoModelo": modelo})
        if isinstance(js, list):
            return [(x["Value"], x["Label"]) for x in js]
        js = self._get_reserva(f"{TIPOS_PARALLELUM[tipo]}/brands/{marca}/models/{modelo}/years",
                               {"reference": ref}) or []
        return [(x["code"], x["name"]) for x in js]

    def preco(self, ref, it):
        """Preço do item no mês de referência; None se a FIPE não tem o item naquele mês;
        levanta RuntimeError se nenhuma das fontes respondeu."""
        js = self._post("ConsultarValorComTodosParametros", {
            "codigoTabelaReferencia": ref, "codigoTipoVeiculo": it["tipo"],
            "codigoMarca": it["marca"], "codigoModelo": it["modelo"],
            "anoModelo": it["ano"], "codigoTipoCombustivel": it["comb"],
            "tipoVeiculo": TIPOS[it["tipo"]], "modeloCodigoExternoFipe": "",
            "tipoConsulta": "tradicional"})
        if js is not None:
            if js.get("Valor"):
                return parse_valor(js["Valor"])
            if js.get("erro") == "nadaencontrado":
                return None
        js = self._get_reserva(f"{TIPOS_PARALLELUM[it['tipo']]}/brands/{it['marca']}/models/{it['modelo']}"
                               f"/years/{it['ano']}-{it['comb']}", {"reference": ref})
        if js is None:
            raise RuntimeError("sem resposta")
        return parse_valor(js.get("price")) if js.get("price") else None


# ---------------------------------------------------------------- cesta
def montar_cesta(fipe, ref, ref_label, prazo):
    ano_ref = parse_mes(ref_label)[0]
    marcas_cache, modelos_cache, itens = {}, {}, []
    for seg, tipo, re_marca, re_modelo, re_excl, nome in CESTA:
        if not fipe.disponivel():
            fipe.esperar(prazo)
        if tipo not in marcas_cache:
            marcas_cache[tipo] = fipe.marcas(ref, tipo)
        marcas = [(c, l) for c, l in marcas_cache[tipo] if re.search(re_marca, l, re.I)]
        if not marcas:
            print(f"[AVISO] Cesta: marca não encontrada para {nome}")
            continue
        candidatos = []
        for marca, marca_nome in marcas:
            chave = (tipo, marca)
            if chave not in modelos_cache:
                modelos_cache[chave] = fipe.modelos(ref, tipo, marca)
            for cod, label in modelos_cache[chave]:
                if re.search(re_modelo, label.strip(), re.I) and not (re_excl and re.search(re_excl, label, re.I)):
                    candidatos.append((marca, marca_nome, cod, label.strip()))
        if not candidatos:
            print(f"[AVISO] Cesta: nenhum modelo encontrado para {nome}")
            continue
        # amostra espalhada pela lista (a FIPE ordena por nome da versão)
        if len(candidatos) > 5:
            passo = len(candidatos) / 5
            candidatos = [candidatos[int(i * passo)] for i in range(5)]
        vivos = []
        for marca, marca_nome, cod, label in candidatos:
            if not fipe.disponivel():
                fipe.esperar(prazo)
            anos = []
            for valor, alabel in fipe.anos(ref, tipo, marca, cod):
                m = re.match(r"(\d{4})-(\d+)", str(valor))
                if m and int(m.group(1)) < 32000:
                    anos.append((int(m.group(1)), int(m.group(2)), alabel))
            if anos and max(a[0] for a in anos) >= ano_ref - 2:
                vivos.append((max(a[0] for a in anos), marca, marca_nome, cod, label, anos))
        vivos.sort(key=lambda v: -v[0])
        for _, marca, marca_nome, cod, label, anos in vivos[:VERSOES_POR_MODELO]:
            anos.sort(reverse=True)
            escolhidos = [anos[0]]
            antigos = [a for a in anos if a[0] <= anos[0][0] - 3]
            if antigos:
                escolhidos.append(antigos[0])
            for ano, comb, alabel in escolhidos:
                itens.append({"id": f"{tipo}-{marca}-{cod}-{ano}-{comb}", "segmento": seg, "grupo": nome,
                              "tipo": tipo, "marca": marca, "marca_nome": marca_nome, "modelo": cod,
                              "versao": label, "ano": ano, "comb": comb, "ano_label": alabel})
        print(f"[INFO] Cesta {nome}: {sum(1 for i in itens if i['grupo'] == nome)} itens", flush=True)
    return {"criada_em": datetime.now(BRT).isoformat(timespec="seconds"), "ref": ref,
            "ref_label": ref_label, "itens": itens}


# ---------------------------------------------------------------- histórico
def atualizar_historico(fipe, cesta, hist, refs, prazo):
    """Busca os preços que faltam. Primeiro o mês atual e o anterior (para o e-mail),
    depois os meses mais antigos, até o prazo (time.monotonic())."""
    precos = hist.setdefault("precos", {})
    alvo = refs[:MESES_HIST]
    ordem = [alvo[:2], alvo[2:]]
    falhas = 0
    for grupo in ordem:
        for ref, _ in grupo:
            for it in cesta["itens"]:
                p = precos.setdefault(it["id"], {})
                if str(ref) in p:
                    continue
                if time.monotonic() > prazo:
                    print("[AVISO] Prazo de coleta esgotado; o restante do histórico fica para o próximo run.")
                    return falhas
                if not fipe.disponivel():
                    fipe.esperar(prazo)
                try:
                    p[str(ref)] = fipe.preco(ref, it)
                except RuntimeError:
                    falhas += 1
    return falhas


# ---------------------------------------------------------------- índices
def variacao(itens, precos, ref_atual, ref_ant):
    logs, detalhes = [], []
    for it in itens:
        p = precos.get(it["id"], {})
        a, b = p.get(str(ref_ant)), p.get(str(ref_atual))
        if a and b:
            logs.append(math.log(b / a))
            detalhes.append((it, b, (b / a - 1) * 100))
    if not logs:
        return None, 0, detalhes
    return (math.exp(sum(logs) / len(logs)) - 1) * 100, len(logs), detalhes


def calcular(cesta, hist, refs):
    precos = hist.get("precos", {})
    alvo = refs[:MESES_HIST]
    grupos = {s: [i for i in cesta["itens"] if i["segmento"] == s] for s in SEGMENTOS}
    grupos["Leves"] = [i for i in cesta["itens"] if i["segmento"] in LEVES]
    colunas = LEVES + ["Leves", "Caminhão", "Moto"]

    mensal = []  # do mais novo para o mais antigo
    for k in range(len(alvo) - 1):
        (ref, label), (ref_ant, _) = alvo[k], alvo[k + 1]
        linha = {"ref": ref, "mes": mes_nome(label), "curto": mes_curto(label), "var": {}, "n": {}}
        for c in colunas:
            v, n, _ = variacao(grupos[c], precos, ref, ref_ant)
            linha["var"][c], linha["n"][c] = v, n
        mensal.append(linha)

    acumulado = {}
    for c in colunas:
        vs = [m["var"][c] for m in mensal if m["var"][c] is not None]
        acumulado[c] = {"var": (math.prod(1 + v / 100 for v in vs) - 1) * 100 if vs else None, "meses": len(vs)}

    destaques = []
    if len(alvo) >= 2:
        _, _, destaques = variacao(cesta["itens"], precos, alvo[0][0], alvo[1][0])

    preco_medio = {}
    for c in colunas:
        vals = [precos.get(i["id"], {}).get(str(alvo[0][0])) for i in grupos[c]]
        vals = [v for v in vals if v]
        preco_medio[c] = sum(vals) / len(vals) if vals else None

    return {"ref": alvo[0][0], "mes": mes_nome(alvo[0][1]),
            "mes_anterior": mes_nome(alvo[1][1]) if len(alvo) > 1 else None,
            "colunas": colunas, "mensal": mensal, "acumulado": acumulado,
            "destaques": destaques, "preco_medio": preco_medio,
            "itens": {c: len(grupos[c]) for c in colunas}}


# ---------------------------------------------------------------- e-mail
def texto_resumo(res):
    m = res["mensal"][0] if res["mensal"] else None
    if not m or m["var"]["Leves"] is None:
        return "Ainda sem dois meses de preços para comparar."
    segs = [(s, m["var"][s]) for s in LEVES + ["Caminhão", "Moto"] if m["var"][s] is not None]
    alta = max(segs, key=lambda x: x[1])
    baixa = min(segs, key=lambda x: x[1])
    v = m["var"]["Leves"]
    verbo = "subiu" if v > 0.05 else "caiu" if v < -0.05 else "ficou estável"
    partes = [f"Na tabela FIPE de {res['mes']}, a cesta de veículos leves {verbo} "
              f"({pct(v, 2)}) frente a {res['mes_anterior']}."]
    r_alta = "maior alta" if alta[1] > 0 else "menor queda"
    r_baixa = "maior queda" if baixa[1] < 0 else "menor alta"
    partes.append(f"Entre os segmentos, {r_alta}: {alta[0]} ({pct(alta[1], 2)}); "
                  f"{r_baixa}: {baixa[0]} ({pct(baixa[1], 2)}).")
    for s in ("Caminhão", "Moto"):
        if m["var"][s] is not None and s not in (alta[0], baixa[0]):
            partes.append(f"{'Caminhões' if s == 'Caminhão' else 'Motos'}: {pct(m['var'][s], 2)}.")
    ac = res["acumulado"]["Leves"]
    if ac["var"] is not None:
        partes.append(f"Acumulado em {ac['meses']} meses (leves): {pct(ac['var'], 1)}.")
    return " ".join(partes)


def montar_email(res, teste=False, falhas=0):
    cols = res["colunas"]
    m0 = res["mensal"][0] if res["mensal"] else {"var": {c: None for c in cols}, "n": {c: 0 for c in cols}}
    resumo = texto_resumo(res)

    body = row(f'<div style="font:15px/1.5 Segoe UI, Roboto, Arial, sans-serif;color:{INK}">{esc(resumo)}</div>',
               pad="14px 16px")

    body += section_title(f"Variação no mês por segmento – {res['mes']}")
    linhas = []
    for c in cols:
        nome = "Leves (geral)" if c == "Leves" else c
        b = c == "Leves"
        ac = res["acumulado"][c]
        linhas.append([f"<b>{esc(nome)}</b>" if b else esc(nome), pct_html(m0["var"][c], 2, bold=True),
                       pct_html(ac["var"]) + (f' <span style="color:{MUTED};font-size:11px">({ac["meses"]}m)</span>'
                                              if ac["meses"] and ac["meses"] < 12 else ""),
                       esc(brl(res["preco_medio"][c])), esc(m0["n"][c])])
    body += data_table(["Segmento", "No mês", "12 meses", "Preço médio cesta", "Itens"], linhas)

    body += section_title("Mês a mês (variação contra o mês anterior)")
    rot = {"Leves": "Leves", "Caminhão": "Caminh.", "Picape": "Picape"}
    mrows = [[esc(m["curto"])] + [pct_html(m["var"][c], 1, bold=(c == "Leves")) for c in cols]
             for m in res["mensal"]]
    body += data_table(["Mês"] + [rot.get(c, c) for c in cols], mrows)

    dest = sorted(res["destaques"], key=lambda d: d[2])
    def tab(lista):
        return [[esc(f"{d[0]['grupo']}") + f'<br><span style="color:{MUTED};font-size:11px">'
                 f'{esc(d[0]["versao"])} · {esc(d[0]["ano"])}</span>', esc(brl(d[1])), pct_html(d[2], 1, True)]
                for d in lista]
    if dest:
        altas = [d for d in reversed(dest) if d[2] > 0][:5]
        quedas = [d for d in dest if d[2] < 0][:5]
        if altas:
            body += section_title("Maiores altas no mês")
            body += data_table(["Modelo", "Preço FIPE", "Var."], tab(altas))
        if quedas:
            body += section_title("Maiores quedas no mês")
            body += data_table(["Modelo", "Preço FIPE", "Var."], tab(quedas))

    footer = (f"Tabela FIPE (veiculos.fipe.org.br), referência {esc(res['mes'])}. A FIPE não separa por "
              f"carroceria: o resumo usa uma cesta fixa de {sum(1 for _ in CESTA)} modelos representativos "
              f"(até {VERSOES_POR_MODELO} versões e 2 anos-modelo de cada, usados). Variação do segmento = média "
              f"geométrica das variações dos itens com preço nos dois meses; Leves = hatch, sedã, SUV e picape.")
    if falhas:
        footer += f" {falhas} consulta(s) sem resposta neste run."

    prefixo = "[Teste] " if teste else ""
    v = m0["var"]["Leves"]
    subject = f"{prefixo}Tabela FIPE {res['mes']}: leves {pct(v, 2)} no mês"
    html = page("RESUMO MENSAL · TABELA FIPE", f"Tabela FIPE – {res['mes']}",
                f"Comparação com {res['mes_anterior']} e últimos 12 meses, por segmento", body, footer)

    texto = [subject, "", resumo, "", f"Variação no mês ({res['mes']}):"]
    for c in cols:
        texto.append(f"  {c:<10} {pct(m0['var'][c], 2):>8}   12m: {pct(res['acumulado'][c]['var'])}")
    texto += ["", "Mês a mês (" + " | ".join(cols) + "):"]
    for m in res["mensal"]:
        texto.append(f"  {m['curto']}: " + " | ".join(pct(m["var"][c]) for c in cols))
    return subject, "\n".join(texto), html


# ---------------------------------------------------------------- demo
def demo_dados():
    refs = []
    ano, mes = 2026, 10
    for k in range(MESES_HIST):
        refs.append((330 + 12 - k, f"{[n for n, v in MESES.items() if v == mes and n != 'marco'][0]}/{ano}"))
        mes -= 1
        if mes == 0:
            ano, mes = ano - 1, 12
    rnd = random.Random(7)
    itens, precos = [], {}
    base = {"Hatch": 80e3, "Sedã": 120e3, "SUV": 150e3, "Picape": 180e3, "Caminhão": 600e3, "Moto": 18e3}
    tend = {"Hatch": -0.3, "Sedã": -0.5, "SUV": -0.2, "Picape": 0.1, "Caminhão": -0.6, "Moto": 0.3}
    for seg, tipo, _, _, _, nome in CESTA:
        for v in range(2):
            for ano_m in (2025, 2022):
                iid = f"{nome}-{v}-{ano_m}"
                itens.append({"id": iid, "segmento": seg, "grupo": nome, "tipo": tipo, "marca": "0",
                              "modelo": "0", "versao": f"Versão {v + 1} 1.0 Flex", "ano": ano_m, "comb": 1})
                p = base[seg] * rnd.uniform(0.7, 1.3) * (0.8 if ano_m == 2022 else 1)
                serie = {}
                for ref, _ in reversed(refs):
                    serie[str(ref)] = round(p, 0)
                    p *= 1 + (tend[seg] + rnd.gauss(0, 0.8)) / 100
                precos[iid] = serie
    return refs, {"itens": itens}, {"precos": precos}


# ---------------------------------------------------------------- principal
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="não envia; salva alerts/fipe_preview.html")
    ap.add_argument("--demo", action="store_true", help="dados simulados, sem internet")
    ap.add_argument("--force", action="store_true", help="envia mesmo que o mês já tenha sido enviado")
    ap.add_argument("--teste", action="store_true", help="marca o assunto com [Teste] e não grava o mês como enviado")
    ap.add_argument("--nova-cesta", action="store_true", help="remonta a cesta de modelos")
    ap.add_argument("--prazo-min", type=float, default=50, help="tempo máximo de coleta de preços (min)")
    args = ap.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    state = load_json(STATE_FILE, {})
    falhas = 0

    if args.demo:
        refs, cesta, hist = demo_dados()
    else:
        fipe = Fipe()
        refs = fipe.referencias()
        if not refs:
            print("[ERRO] Não consegui ler as tabelas de referência da FIPE.", file=sys.stderr)
            return 1
        ref, label = refs[0]
        print(f"[INFO] Tabela FIPE mais recente: {label} (código {ref})")
        ja_enviado = not args.force and state.get("ultimo_enviado") == ref
        if ja_enviado:
            print("[INFO] Esse mês já foi enviado; só completo o histórico, sem e-mail.")
        prazo = time.monotonic() + args.prazo_min * 60

        cesta = load_json(CESTA_FILE, None)
        if args.nova_cesta or not cesta or not cesta.get("itens"):
            print("[INFO] Montando a cesta de modelos…", flush=True)
            cesta = montar_cesta(fipe, ref, label, prazo)
            save_json(CESTA_FILE, cesta)
        print(f"[INFO] Cesta: {len(cesta['itens'])} itens", flush=True)

        hist = load_json(HIST_FILE, {})
        try:
            falhas = atualizar_historico(fipe, cesta, hist, refs, prazo)
        finally:
            hist["refs"] = {str(r): l for r, l in refs[:MESES_HIST]}
            hist["atualizado_em"] = datetime.now(BRT).isoformat(timespec="seconds")
            save_json(HIST_FILE, hist)
        if ja_enviado:
            print(f"[INFO] Consultas: FIPE {fipe.calls}, reserva {fipe.reserva_calls}, falhas {falhas}")
            return 0
        print(f"[INFO] Consultas: FIPE {fipe.calls}, reserva {fipe.reserva_calls}, falhas {falhas}")

    res = calcular(cesta, hist, refs)
    subject, text, html = montar_email(res, teste=args.teste, falhas=falhas)
    print(text)

    if not args.demo:
        save_json(RESUMO_FILE, {k: v for k, v in res.items() if k != "destaques"} | {
            "resumo": texto_resumo(res), "gerado_em": datetime.now(BRT).isoformat(timespec="seconds")})

    if args.dry_run:
        PREVIEW_FILE.write_text(html, encoding="utf-8")
        print(f"[INFO] Prévia salva em {PREVIEW_FILE}")
        return 0

    m0 = res["mensal"][0] if res["mensal"] else None
    if not m0 or m0["var"]["Leves"] is None:
        print("[ERRO] Sem preços suficientes para comparar dois meses; e-mail não enviado.", file=sys.stderr)
        return 1

    send_email(subject, text, html)
    print("[INFO] E-mail enviado.")
    if not args.teste and not args.demo:
        state["ultimo_enviado"] = res["ref"]
        state["enviado_em"] = datetime.now(BRT).isoformat(timespec="seconds")
        save_json(STATE_FILE, state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
