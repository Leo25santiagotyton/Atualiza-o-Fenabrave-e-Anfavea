"""
Aba Carteira do painel: posições dos fundos de crédito da Tyton nos emissores acompanhados
(transportes e bens de capital), lidas do PDF diário "Controle Operacional Crédito" (SharePoint).

  python3 tools/carteira_build.py <pasta com AAAA-MM-DD.txt> <saída.json> [--base carteira_atual.json] [--arquivo "nome do PDF"]

Com --base, junta o histórico (hist, plHist, saidas) do documento atual do painel aos PDFs da pasta:
basta pôr na pasta só o PDF do dia novo.

Cada .txt é o texto do PDF como o conector do Microsoft 365 devolve. Os dados ficam só no
banco do artifact (debentures/carteira); não vão para o repositório.
"""
import json, os, re, sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
from carteira_parse import load, parse

# devedor no relatório -> emissor como o painel chama
EMISSORES = [
    (r"vamos", "Vamos"), (r"movida", "Movida"), (r"simpar", "Simpar"), (r"\bjsl\b", "JSL"),
    (r"localiza", "Localiza"), (r"armac", "Armac"), (r"randon", "Randoncorp"), (r"fras", "Frasle"),
    (r"priner", "Priner"), (r"tupy", "Tupy"), (r"automob", "Automob"), (r"\bohi\b", "OHI"),
    (r"borr", "Borr Drilling"), (r"foresea", "Foresea"), (r"constellation", "Constellation"), (r"\bchc\b", "CHC"),
]
BOND_ISIN = {"OHIFLY00001": "US67712MAB54"}


def emissor(dev):
    for rx, nome in EMISSORES:
        if re.search(rx, dev, re.I):
            return nome
    return None


def main(pasta, saida, base=None, arquivo=None):
    dias = sorted(f[:10] for f in os.listdir(pasta) if re.match(r"\d{4}-\d{2}-\d{2}\.txt$", f))
    hist, plh, ultimo, emi = {}, [], None, {}
    if base:
        b = json.load(open(base, encoding="utf-8"))
        hist = {t: [x for x in h if x[0] not in dias] for t, h in (b.get("hist") or {}).items()}
        plh = [x for x in (b.get("plHist") or []) if x[0] not in dias]
        for a in (b.get("ativos") or []) + (b.get("saidas") or []):
            emi[a["ticker"]] = a["emissor"]
    for d in dias:
        r = parse(load(os.path.join(pasta, d + ".txt")))
        data = r["data"] or d
        plh.append([data, round(r["pl"].get("Total", 0))])
        for x in r["rows"]:
            if not emissor(x["devedor"]):
                continue
            emi[x["ticker"]] = emissor(x["devedor"])
            hist.setdefault(x["ticker"], []).append(
                [data, round(x["fin"], 2), x.get("qtd"), x.get("mtm"),
                 {f: round(v["fin"]) for f, v in x["fundos"].items()}])
        if ultimo is None or data >= ultimo[0]:
            ultimo = (data, r)
    for h in hist.values():
        h.sort()
    plh.sort()
    data, r = ultimo
    ativos = []
    for x in r["rows"]:
        e = emissor(x["devedor"])
        if not e:
            continue
        a = {k: x.get(k) for k in ("ticker", "tipo", "index", "inst", "risco", "dur", "venc", "emiss", "mtm",
                                   "devedor", "setor", "fin", "qtd", "aloc")}
        a["emissor"] = e
        a["fundos"] = {f: {"fin": round(v["fin"], 2), "aloc": v["aloc"]} for f, v in x["fundos"].items()}
        a["isin"] = BOND_ISIN.get(x["ticker"])
        ativos.append(a)
    ativos.sort(key=lambda a: -a["fin"])
    atuais = {a["ticker"] for a in ativos}
    saidas = [{"ticker": t, "emissor": emi[t], "ultimo": h[-1][0], "fin": h[-1][1]}
              for t, h in hist.items() if t not in atuais]
    saidas.sort(key=lambda x: x["ultimo"], reverse=True)
    now = datetime.now(timezone(timedelta(hours=-3)))
    out = {"updatedAt": now.isoformat(timespec="seconds"), "data": data,
           "fonte": f"Controle Operacional Crédito de {data[8:10]}/{data[5:7]}/{data[:4]}",
           "pl": {k: round(v, 2) for k, v in r["pl"].items()}, "plHist": plh,
           "arquivo": arquivo, "ativos": ativos, "saidas": saidas, "hist": hist}
    json.dump(out, open(saida, "w", encoding="utf-8"), ensure_ascii=False)
    print(data, len(ativos), "ativos", len(dias), "dias", os.path.getsize(saida), "bytes")


if __name__ == "__main__":
    args = sys.argv[1:]
    base = args[args.index("--base") + 1] if "--base" in args else None
    arquivo = args[args.index("--arquivo") + 1] if "--arquivo" in args else None
    main(args[0], args[1], base, arquivo)
