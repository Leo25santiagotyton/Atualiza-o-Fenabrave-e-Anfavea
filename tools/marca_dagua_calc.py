"""Acrescenta ao JSON da marca d'água (saída do marca_dagua_parse.py) os papéis CDI+ do painel que não
estão na planilha "Controle Marca DAgua", calculados pelo mesmo método da planilha:

    marca d'água = (1 + spread de emissão) / (Call Price / PU par) ^ (1 / duration) - 1

com Call Price / PU par = (1 + prêmio) ^ (DU entre o resgate e o vencimento / 252) no prêmio pro rata
e (1 + prêmio) no prêmio flat, e a duration (anos) da ANBIMA do último dia. A data de resgate é a do
próximo dia útil se a janela de resgate já abriu, senão a data em que abre.

Os termos de resgate (data a partir da qual pode resgatar, prêmio e tipo) vêm das escrituras públicas
(CVM) e ficam em alerts/resgate_termos.json: {"papeis": {"COD": {"desde": "AAAA-MM-DD",
"premios": [["AAAA-MM-DD", 0.55], ...], "tipo": "Pro Rata"|"Flat", "fonte": "..."}}}.

Uso: python tools/marca_dagua_calc.py <marca.json>   (reescreve o arquivo)
"""
import json, re, sys, datetime, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
FERIADOS = {  # feriados nacionais fixos; os móveis entram pela lista abaixo
    (1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)}
MOVEIS = {"2026-02-16", "2026-02-17", "2026-04-03", "2026-06-04", "2027-02-08", "2027-02-09", "2027-03-26",
          "2027-05-27", "2028-02-28", "2028-02-29", "2028-04-14", "2028-06-15", "2029-02-12", "2029-02-13",
          "2029-03-30", "2029-05-31", "2030-03-04", "2030-03-05", "2030-04-19", "2030-06-20", "2031-02-24",
          "2031-02-25", "2031-04-11", "2031-06-12", "2032-02-09", "2032-02-10", "2032-03-26", "2032-05-27",
          "2033-02-28", "2033-03-01", "2033-04-15", "2033-06-16", "2034-02-20", "2034-02-21", "2034-04-07",
          "2034-06-08"}


def util(d):
    return d.weekday() < 5 and (d.month, d.day) not in FERIADOS and d.isoformat() not in MOVEIS


def du(a, b):
    n, d = 0, a
    while d < b:
        if util(d):
            n += 1
        d += datetime.timedelta(1)
    return n


def prox_util(d):
    d += datetime.timedelta(1)
    while not util(d):
        d += datetime.timedelta(1)
    return d


def dur_fluxo(call, e, venc, agenda):
    """Duration (anos, a partir do resgate) pelo fluxo da agenda do SND: juros a e e amortizações iguais
    nas datas de amortização restantes. Só para papéis sem duration ANBIMA (aproximação)."""
    iso = lambda x: datetime.date.fromisoformat(x)
    ams = sorted({iso(a[0]) for a in agenda if a[1].startswith("Amort") and iso(a[0]) > call} | {venc})
    jur = sorted({iso(a[0]) for a in agenda if a[1] == "Juros" and iso(a[0]) > call} | {venc})
    bal, last, k, out = 1.0, call, 0, []
    for d in sorted(set(jur) | set(ams)):
        f = (1 + e) ** (du(last, d) / 252)
        am = bal / (len(ams) - k) if d in ams else 0
        k += d in ams
        out.append((du(call, d) / 252, bal * (f - 1) + am))
        bal -= am
        last = d
    pv = [c / (1 + e) ** t for t, c in out]
    return sum(t * v for (t, _), v in zip(out, pv)) / sum(pv) if pv else None


def spread(det):
    s = det.get("Juros/Spread") or ""
    m = re.match(r"\s*(\d+(?:,\d+)?)", s)
    return float(m.group(1).replace(",", ".")) / 100 if m and "DI" in (det.get("Tipo de Remuneração") or "").upper() else None


def main():
    path = sys.argv[1]
    doc = json.load(open(path, encoding="utf-8"))
    termos = ROOT / "alerts" / "resgate_termos.json"
    if not termos.exists():
        print("sem alerts/resgate_termos.json: nada a calcular")
        return
    T = json.load(open(termos, encoding="utf-8"))["papeis"]
    papers = {p["code"]: p for p in json.load(open(ROOT / "alerts/debentures_painel.json", encoding="utf-8"))["papers"]}
    fich = json.load(open(ROOT / "alerts/debentures_fichas.json", encoding="utf-8"))["fichas"]
    hoje = datetime.date.today()
    n = 0
    for code, t in T.items():
        if code in doc["papeis"] or code not in papers:
            continue
        det = fich.get(code, {}).get("details", {})
        e = spread(det)
        venc = det.get("Vencimento")
        ser = [x for x in papers[code].get("series", []) if x[1] is not None and x[3]]
        if e is None or not venc or not t.get("desde"):
            continue
        venc = datetime.date(*map(int, reversed(venc.split("/"))))
        desde = datetime.date.fromisoformat(t["desde"])
        call = max(prox_util(hoje), desde)
        if call >= venc:
            continue
        prem = None
        for d0, p in sorted(t.get("premios") or []):
            if datetime.date.fromisoformat(d0) <= call:
                prem = p
        if prem is None and t.get("premios"):
            prem = sorted(t["premios"])[0][1]
        if prem is None:
            continue
        nr = du(call, venc) / 252
        ratio = (1 + prem / 100) ** nr if (t.get("tipo") or "Pro Rata").lower().startswith("pro") else 1 + prem / 100
        D = ser[-1][3] / 252 if ser else dur_fluxo(call, e, venc, fich.get(code, {}).get("agenda") or [])
        if not D or D <= 0:
            continue
        md = ((1 + e) / ratio ** (1 / D) - 1) * 100
        doc["papeis"][code] = {"md": round(md, 4), "venc": venc.isoformat(), "resgate": call.isoformat(),
                               "tipo": t.get("tipo") or "Pro Rata", "premio": prem, "fonte": "calc",
                               "obs": ("calculado pelo método da planilha com a duration ANBIMA de " + ser[-1][0] if ser else
                                       "aproximado: sem taxa ANBIMA, duration estimada pela agenda do SND")
                                      + ("; resgate ainda não aberto, a duration a partir do resgate seria menor" if ser and desde > prox_util(hoje) else ""),
                               **({"aprox": True} if not ser else {})}
        n += 1
    json.dump(doc, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(n, "papéis calculados")


if __name__ == "__main__":
    main()
