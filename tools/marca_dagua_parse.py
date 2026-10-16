"""Lê o texto do read_resource da planilha "Controle Marca DAgua.xlsx" (aba "Transposto (Inputs)")
e grava um JSON {data, papeis: {TICKER: {...}}} para o banco do painel (debentures/marca).

Uso: python tools/marca_dagua_parse.py <texto_da_planilha.txt> <saida.json> [AAAA-MM-DD]
Os dados da planilha são internos: o JSON vai só para o banco do painel, nunca para o repositório.
"""
import json, re, sys, datetime


def num(s):
    s = (s or "").replace("R$", "").replace("%", "").replace(" ", "").strip()
    if not s or s in ("-", "FALSO", "VERDADEIRO"):
        return None
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def iso(s):
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", (s or "").strip())
    return f"{m[3]}-{m[2]}-{m[1]}" if m else None


def main():
    txt = open(sys.argv[1], encoding="utf-8").read().split("\n")
    i = next(k for k, l in enumerate(txt) if l.startswith("## Sheet: Transposto (Inputs)"))
    rows = {}
    for l in txt[i + 1:]:
        if l.startswith("## Sheet") or l.startswith("Formulas:"):
            break
        f = l.split("\t")
        if len(f) > 3 and f[1].strip():
            rows.setdefault(f[1].strip(), f[2:])
    tk = [t.strip() for t in rows["Ticker do Ativo"]]
    g = lambda k, j: (rows.get(k) or [])[j].strip() if j < len(rows.get(k) or []) else ""
    out = {}
    for j, t in enumerate(tk):
        if not t:
            continue
        md = num(g("Taxa Marca Dagua", j))
        md2 = num(g("Taxa Marca Dagua 2", j))
        out[t] = {k: v for k, v in {
            "md": round(md, 4) if md is not None else None,
            "md2": round(md2, 4) if md2 else None,
            "venc": iso(g("Data Vencimento", j)), "resgate": iso(g("Data de Resgate", j)),
            "resgate2": iso(g("Data de Resgate 2", j)), "tipo": g("Tipo de Prêmio", j) or None,
            "premio": num(g("Prêmio de Resgate", j)), "puPar": num(g("PU Par at Call", j)),
            "callPrice": num(g("Call Price", j)), "fonte": "planilha",
        }.items() if v not in (None, "")}
    data = sys.argv[3] if len(sys.argv) > 3 else datetime.date.today().isoformat()
    json.dump({"data": data, "fonte": "Controle Marca DAgua.xlsx (aba Transposto (Inputs))",
               "updatedAt": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "papeis": out},
              open(sys.argv[2], "w"), ensure_ascii=False, separators=(",", ":"))
    print(len(out), "papéis;", sum(1 for v in out.values() if v.get("md") is not None), "com taxa")


if __name__ == "__main__":
    main()
