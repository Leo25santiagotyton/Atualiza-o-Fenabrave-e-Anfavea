"""
Lê o texto da lâmina diária de um fundo de crédito da Tyton (HY, Crédito, Prev, Prev IQ) e devolve,
para os papéis pedidos: taxa de emissão, taxa de compra (TX Comp), marcação e suas variações, retornos
e carrego; mais as movimentações (compras/vendas com taxa), os retornos do fundo e a tabela de pares.

  python3 tools/lamina_parse.py <texto.txt> [TICKER ...]
"""
import json, re, sys


def num(s):
    s = s.strip().replace("R$", "").replace("%", "").replace("−", "-").strip()
    if s in ("", "-", "—"):
        return None
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def toks(seg):
    return [x.strip() for x in re.split(r"\s{2,}", seg) if x.strip()]


def secao(t, ini, fins):
    i = t.find(ini)
    if i < 0:
        return ""
    j = min([k for k in (t.find(f, i + len(ini)) for f in fins) if k > 0] or [len(t)])
    return t[i:j]


def linhas(tk, tickers, n):
    """acha cada ticker na lista de tokens e devolve os n tokens seguintes"""
    out = {}
    for i, x in enumerate(tk):
        if x in tickers and x not in out:
            out[x] = tk[i + 1:i + 1 + n]
    return out


def parse(t, tickers):
    t = t.replace(" ", " ")
    m = re.search(r"(TYTON CR[ÉE]DITO[A-ZÉ ]*?)\s{2,}(\d{1,2}) de (\w+) de (\d{4})", t)
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    data = f"{m.group(4)}-{meses.index(m.group(3).lower()) + 1:02d}-{int(m.group(2)):02d}" if m else None
    nome = m.group(1).strip() if m else None
    ativos = {}
    # CDI+: Venc Dur [%pupar] Emis Comp Mtm vDia vSem vMes vAno rDia%CDI cDia rMes%CDI cMes rAno rAno%CDI carAno cAno Qtde Vol Carrego Aloc
    cdi = toks(secao(t, "Carteira de Crédito (CDI+)", ["Carteira de Fundos", "Carteira Offshore", "Carteira de Crédito (IPCA+)"]))
    for tick, r in linhas(cdi, tickers, 22).items():
        if len(r) > 2 and r[2].endswith("%"):
            r = r[:2] + r[3:]
        if len(r) < 21:
            continue
        ativos[tick] = {"perna": "CDI+", "venc": r[0], "dur": num(r[1]), "emis": num(r[2]), "comp": num(r[3]), "mtm": num(r[4]),
                        "vDia": num(r[5]), "vSem": num(r[6]), "vMes": num(r[7]), "vAno": num(r[8]),
                        "rMesCdi": num(r[11]), "rAno": num(r[13]), "rAnoCdi": num(r[14]), "carAno": num(r[15]),
                        "qtde": num(r[17]), "fin": num(r[18]), "aloc": num(r[20])}
    # IPCA+: Inst Indice Venc Dur Emis Comp Mtm vDia vSem vAno rDia netDia dia%CDI cDia rMes netMes mes%CDI cMes rAno netAno ano%CDI cAno Qtde Vol Carrego Aloc
    ipca = toks(secao(t, "Carteira de Crédito (IPCA+)", ["BMF", "Carteira de Fundos", "Carteira Offshore", "Rentabilidade"]))
    for tick, r in linhas(ipca, tickers, 26).items():
        if len(r) < 26:
            continue
        ativos[tick] = {"perna": "IPCA+", "venc": r[2], "dur": num(r[3]), "emis": num(r[4]), "comp": num(r[5]), "mtm": num(r[6]),
                        "vDia": num(r[7]), "vSem": num(r[8]), "vAno": num(r[9]),
                        "rMes": num(r[14]), "rMesNet": num(r[15]), "rMesCdi": num(r[16]), "rAno": num(r[18]), "rAnoNet": num(r[19]),
                        "rAnoCdi": num(r[20]), "qtde": num(r[22]), "fin": num(r[23]), "aloc": num(r[25])}
    # Offshore: Devedor Index Venc Dur Emis | Dia USD BRL Hedge Net Net%CDI | Mês ... | Ano ... | Qtde Vol Aloc
    off = toks(secao(t, "Carteira Offshore", ["Carteira de Crédito (IPCA+)", "BMF", "Rentabilidade", "Carteira de Fundos"]))
    for tick, r in linhas(off, tickers, 23).items():
        if len(r) < 23:
            continue
        ativos[tick] = {"perna": "USD", "venc": r[2], "dur": num(r[3]), "emis": num(r[4]),
                        "dia": {"usd": num(r[5]), "brl": num(r[6]), "hedge": num(r[7]), "net": num(r[8])},
                        "mes": {"usd": num(r[10]), "brl": num(r[11]), "hedge": num(r[12]), "net": num(r[13]), "netCdi": num(r[14])},
                        "ano": {"usd": num(r[15]), "brl": num(r[16]), "hedge": num(r[17]), "net": num(r[18]), "netCdi": num(r[19])},
                        "qtde": num(r[20]), "fin": num(r[21]), "aloc": num(r[22])}
    # movimentações: Data Side Ativo Qtd [Tx] Financeiro
    mov = []
    sm = secao(t, "Movimentações", ["Caixa Futuro", "CENÁRIO BASE", "‹"])
    for m2 in re.finditer(r"(\d{2}/\d{2}/\d{4})\s{2,}([CV])\s{2,}(.+?)\s{2,}([\d.]+)\s{2,}(?:([\d.,-]+)\s{2,})?R\$\s?([\d.,-]+)", sm):
        if m2.group(3) in tickers:
            d = m2.group(1)
            mov.append({"data": f"{d[6:]}-{d[3:5]}-{d[:2]}", "lado": m2.group(2), "ativo": m2.group(3), "qtd": num(m2.group(4)),
                        "tx": num(m2.group(5)) if m2.group(5) else None, "fin": num(m2.group(6))})
    # retornos do fundo (primeira linha da tabela Retornos) e do CDI
    ret = {}
    sr = secao(t, "Retornos  Índice", ["Carteira de Crédito"])
    if sr:
        tk = toks(sr)
        hdr = []
        for x in tk[1:]:
            if re.match(r"^-?[\d.,]+%$", x):
                break
            hdr.append(x)
        rows, cur = [], None
        for x in tk[1 + len(hdr):]:
            if re.match(r"^-?[\d.,]+%$", x):
                if cur is None:
                    cur = ("__fundo__", []); rows.append(cur)
                cur[1].append(num(x))
            else:
                cur = (x, []); rows.append(cur)
        hdr = [h for h in hdr if h != "Índice"]
        if hdr and hdr[-1] not in ("Dia", "Semana", "Mês", "Ano", "Inicio", "Início") and not re.search(r"Mes|Mês", hdr[-1]):
            first = hdr.pop()
            if rows and rows[0][0] != first:
                pass
            # os valores antes do primeiro nome de linha são do próprio fundo
        else:
            first = None
        ret = {"periodos": hdr, "linhas": [{"nome": a, "v": b} for a, b in rows]}
        for l in ret["linhas"]:
            if l["nome"] == "__fundo__":
                l["nome"] = first or "Fundo"
    # pares comparáveis: nome [★] [IQ|IP|▬] Dia Semana Mês Ano %CDI 12M ...
    pares = []
    tk = toks(secao(t, "Peers Comparáveis", ["Todos Peers", "‹"]))
    pct = lambda x: re.match(r"^-?[\d.,]+%$", x)
    for i, x in enumerate(tk):
        if pct(x) or x in ("★", "IQ", "IP", "▬") or i + 7 >= len(tk):
            continue
        j = i + 1
        while j < len(tk) and tk[j] in ("★", "IQ", "IP", "▬"):
            j += 1
        v = tk[j:j + 6]
        if len(v) == 6 and all(pct(y) for y in v[:5]):
            pares.append({"fundo": x, "tyton": "★" in tk[i + 1:j], "mes": num(v[2]), "ano": num(v[3]), "anoCdi": num(v[4]),
                          "m12": num(v[5]) if pct(v[5]) else None})
    return {"fundo": nome, "data": data, "ativos": ativos, "movs": mov, "retornos": ret, "pares": pares}


if __name__ == "__main__":
    r = parse(open(sys.argv[1], encoding="utf-8").read(), set(sys.argv[2:]))
    print(json.dumps(r, ensure_ascii=False, indent=1)[:6000])
