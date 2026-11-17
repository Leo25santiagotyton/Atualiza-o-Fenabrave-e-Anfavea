"""
Cronograma de amortização das debêntures por empresa
----------------------------------------------------
Lê alerts/debentures.json (ficha e agenda de eventos de cada papel no SND, gravadas por debentures_anbima.py) e
monta, para cada debênture ainda em mercado, quanto do principal vence em cada data:

  - quantidade em mercado (ficha do SND, campo "Mercado") × valor nominal de emissão = principal de face;
  - datas de amortização e o vencimento pela agenda de eventos do SND. Quando o SND não informa o percentual
    de cada parcela (o caso comum, "VNA VAR/UNIF" etc.), o principal é dividido em parcelas iguais entre todas
    as datas de amortização da agenda (passadas e futuras); as já pagas saem do saldo.
  - sem agenda publicada: considerado bullet no vencimento.

É uma estimativa do principal de face (não corrige pelo IPCA nem inclui juros); a fonte oficial é a escritura.
Grava alerts/debentures_cronograma.json (vai para o painel em debentures/cronograma).
"""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).parent / "alerts"
SRC = BASE / "debentures.json"
OUT = BASE / "debentures_cronograma.json"
BRT = timezone(timedelta(hours=-3))


def _num(s):
    s = str(s or "").replace("R$", "").strip()
    m = re.search(r"-?[\d.]+(?:,\d+)?", s)
    if not m:
        return None
    return float(m.group(0).replace(".", "").replace(",", "."))


def _iso(s):
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", str(s or ""))
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def cronograma(p, hoje):
    det = p.get("details") or {}
    q = _num(det.get("Mercado"))
    if q is None:
        m = re.search(r"Mercado:\s*([\d.]+)", det.get("Quantidades", ""))
        q = _num(m.group(1)) if m else None
    vn = _num(det.get("Nominal na Emissão"))
    venc = _iso(det.get("Data do Novo Vencimento")) or _iso(det.get("Vencimento")) or p.get("maturity")
    if not q or not vn or not venc or venc < hoje:
        return None
    # eventos de principal na agenda: [iso, data, emissor, evento, detalhe, ...]
    datas, pct = {}, {}
    for e in p.get("agenda") or []:
        txt = [str(x) for x in e[1:]]
        ev = next((x for x in txt if re.search(r"amortiza|vencimento|resgate", x, re.I)), None)
        if not ev:
            continue
        datas[e[0]] = ev
        num = next((x for x in txt if re.fullmatch(r"\d{1,3},\d{2,}", x.strip())), None)
        if num and re.search(r"amortiza", ev, re.I):
            pct[e[0]] = float(num.replace(",", ".")) / 100
    datas.setdefault(venc, "Vencimento")
    ds = sorted(d for d in datas if d <= venc)
    if len(ds) == 1:
        tipo = "bullet" if p.get("agenda") else "bullet (agenda não publicada)"
        fr = {ds[0]: 1.0}
    else:
        tipo = f"{len(ds)} parcelas"
        fr, resto = {}, 1.0
        if pct:  # percentuais informados: sobre o saldo (VNA); a última leva o que sobrar
            for d in ds[:-1]:
                v = resto * pct.get(d, 1 / (len(ds) - ds.index(d)))
                fr[d], resto = v, resto - v
            fr[ds[-1]] = resto
            tipo += " (% do SND)"
        else:
            fr = {d: 1 / len(ds) for d in ds}
    fut = [[d, fr[d]] for d in ds if d >= hoje]
    pago = sum(fr[d] for d in ds if d < hoje)
    if not fut or 1 - pago <= 1e-9:
        return None
    face = q * vn
    return {"code": p["code"], "issuer": p.get("issuer"), "ticker": p.get("ticker"), "index": p.get("index") or det.get("Tipo de Remuneração"),
            "emissao": _iso(det.get("Emissão")), "venc": venc, "q": q, "vn": vn,
            "saldo": round(face * (1 - pago), 2),
            "parc": [[d, round(face * f, 2)] for d, f in fut], "tipo": tipo,
            "amort_snd": (det.get("Tipo de Amortização") or "")[:70]}


def main():
    d = json.loads(SRC.read_text(encoding="utf-8"))
    hoje = datetime.now(BRT).date().isoformat()
    out = []
    for p in d.get("papers", []):
        if p.get("section") in ("CRA", "CRI"):
            continue
        c = cronograma(p, hoje)
        if c:
            out.append(c)
    out.sort(key=lambda c: (c["issuer"] or "", c["venc"]))
    doc = {"updatedAt": d.get("updatedAt"), "gerado_em": datetime.now(BRT).isoformat(timespec="seconds"), "papeis": out,
           "metodo": "Principal de face = quantidade em mercado (SND) × valor nominal de emissão, dividido em parcelas iguais "
                     "entre as datas de amortização da agenda do SND quando o percentual não é informado; sem agenda, bullet. "
                     "Não corrige pelo IPCA nem inclui juros. Fonte oficial: escritura."}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tot = {}
    for c in out:
        tot[c["issuer"]] = tot.get(c["issuer"], 0) + c["saldo"]
    print(f"[OK] cronograma: {len(out)} debêntures; " + ", ".join(f"{k} R$ {v / 1e6:,.0f} mi" for k, v in sorted(tot.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    main()
