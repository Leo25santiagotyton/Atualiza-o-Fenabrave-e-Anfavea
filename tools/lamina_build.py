"""
Junta as lâminas diárias dos 4 fundos de crédito num documento só para a aba Carteira do painel
(debentures/laminas): taxa de compra, marcação e retornos por fundo de cada papel acompanhado,
movimentações (compras/vendas com taxa), retornos dos fundos e a tabela de pares.

  python3 tools/lamina_build.py <carteira.json> <saída.json> HY=<txt> Cred=<txt> Prev=<txt> PrevIQ=<txt> [--base laminas_atual.json]

Os tickers vêm da carteira (ativos atuais e os que saíram). Com --base, as movimentações antigas são mantidas.
"""
import json, os, sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
from lamina_parse import parse


def main(cart, saida, arqs, base=None):
    c = json.load(open(cart, encoding="utf-8"))
    tick = {a["ticker"] for a in c.get("ativos", [])} | {a["ticker"] for a in c.get("saidas", [])}
    fundos, pares, datas = {}, [], []
    for f, p in arqs.items():
        r = parse(open(p, encoding="utf-8").read(), tick)
        datas.append(r["data"])
        fundos[f] = {"nome": r["fundo"], "data": r["data"], "retornos": r["retornos"], "ativos": r["ativos"]}
        if len(r["pares"]) > len(pares):
            pares = r["pares"]
        for m in r["movs"]:
            m["fundo"] = f
    movs = [dict(m, fundo=f) for f, p in arqs.items() for m in parse(open(p, encoding="utf-8").read(), tick)["movs"]]
    if base and os.path.exists(base):
        b = json.load(open(base, encoding="utf-8"))
        chave = lambda m: (m["fundo"], m["data"], m["lado"], m["ativo"], m["qtd"])
        vistos = {chave(m) for m in movs}
        movs += [m for m in b.get("movs", []) if chave(m) not in vistos]
    movs.sort(key=lambda m: (m["data"], m["ativo"]), reverse=True)
    now = datetime.now(timezone(timedelta(hours=-3)))
    out = {"updatedAt": now.isoformat(timespec="seconds"), "data": max(d for d in datas if d),
           "fundos": fundos, "movs": movs, "pares": pares}
    json.dump(out, open(saida, "w", encoding="utf-8"), ensure_ascii=False)
    print(out["data"], {f: len(v["ativos"]) for f, v in fundos.items()}, len(movs), "movs", len(pares), "pares", os.path.getsize(saida), "bytes")


if __name__ == "__main__":
    a = sys.argv[1:]
    base = a[a.index("--base") + 1] if "--base" in a else None
    arqs = dict(x.split("=", 1) for x in a[2:] if "=" in x)
    main(a[0], a[1], arqs, base)
