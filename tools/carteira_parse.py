"""Lê o texto do PDF 'Controle Operacional Crédito' e devolve PLs e posições (crédito, fundos, offshore)."""
import json, re, sys

def num(s):
    return float(s.replace('.', '').replace(',', '.'))

FUNDS = ["HY", "Cred", "PrevIQ", "Prev"]

def load(path):
    t = open(path, encoding='utf-8').read()
    try:
        d = json.loads(t); t = d.get('content') or d.get('text') or t
    except Exception:
        pass
    return t

def parse(t):
    tok = [x.strip() for x in re.split(r'\s{2,}', t) if x.strip()]
    pl = {}
    for name, key in [("PL HY", "HY"), ("PL Cred", "Cred"), ("PL Prev IQ", "PrevIQ"), ("PL Prev", "Prev"), ("PL Total", "Total")]:
        for i, x in enumerate(tok):
            if x == name and i > 0 and key not in pl:
                pl[key] = num(tok[i - 1]); break
    m = re.search(r'Data do dado por fundo:\s*HY\s+(\d{2}/\d{2})', t)
    md = re.search(r'CONTROLE OPERACIONAL CR[ÉE]DITO\s+(\d{1,2}) de (\w+) de (\d{4})', t)
    meses = ["janeiro","fevereiro","março","abril","maio","junho","julho","agosto","setembro","outubro","novembro","dezembro"]
    data = None
    if md:
        data = f"{md.group(3)}-{meses.index(md.group(2).lower())+1:02d}-{int(md.group(1)):02d}"
    rows = []
    # crédito
    a = t.find('Carteira de Credito'); b = t.find('Carteira de Fundos')
    sec = [x.strip() for x in re.split(r'\s{2,}', t[a:b]) if x.strip()]
    i = 0
    idx_re = re.compile(r'^(CDI\+|IPCA\+|%CDI|PRE|Pré|IGPM\+|CDI|USD)$')
    starts = [j for j in range(len(sec) - 2) if idx_re.match(sec[j + 1]) and re.match(r'^\d{4}-\d{2}$', sec[j + 5] if j + 5 < len(sec) else '')]
    for k, j in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(sec)
        r = sec[j:end]
        tick, idx, inst, risco, dur, venc, emiss, mtm, dev, setor = r[:10]
        nums = r[10:]
        if nums and nums[-1] == 'TOTAL': nums = nums[:-1]
        trip = []
        q = 0
        while q + 2 < len(nums) and re.match(r'^-?[\d.]+$', nums[q]) and nums[q + 2].endswith('%'):
            trip.append((num(nums[q]), num(nums[q + 1]), num(nums[q + 2][:-1]))); q += 3
        if not trip: continue
        total = trip[-1]; per = {}
        for fin, qtd, al in trip[:-1]:
            best = min(FUNDS, key=lambda f: abs(fin / (al / 100) - pl.get(f, 1e18)) if al else 1e18)
            per[best] = {"fin": fin, "qtd": qtd, "aloc": al}
        if len(trip) == 1:
            fin, qtd, al = total
            best = min(FUNDS, key=lambda f: abs(fin / (al / 100) - pl.get(f, 1e18)) if al else 1e18)
            per[best] = {"fin": fin, "qtd": qtd, "aloc": al}
        rows.append({"tipo": "credito", "ticker": tick, "index": idx, "inst": inst, "risco": risco, "dur": num(dur), "venc": venc,
                     "emiss": num(emiss), "mtm": num(mtm), "devedor": dev, "setor": setor,
                     "fin": total[0], "qtd": total[1], "aloc": total[2], "fundos": per})
    # offshore
    a = t.find('Offshore  Codigo'); b = t.find('TOTAL', a)
    if a > 0:
        sec = [x.strip() for x in re.split(r'\s{2,}', t[a:b]) if x.strip()]
        for j, x in enumerate(sec):
            if x in ('Bond',) and j >= 3:
                code, dev, idx = sec[j - 3], sec[j - 2], sec[j - 1]
                risco, venc, emiss, setor = sec[j + 1], sec[j + 2], sec[j + 3], sec[j + 4]
                nums = sec[j + 5:]; trip = []
                q = 0
                while q + 1 < len(nums) and re.match(r'^-?[\d.]+$', nums[q]) and nums[q + 1].endswith('%'):
                    trip.append((num(nums[q]), num(nums[q + 1][:-1]))); q += 2
                if not trip: continue
                per = {}
                for fin, al in trip[:-1]:
                    best = min(FUNDS, key=lambda f: abs(fin / (al / 100) - pl.get(f, 1e18)) if al else 1e18)
                    per[best] = {"fin": fin, "aloc": al}
                rows.append({"tipo": "offshore", "ticker": code, "index": idx, "inst": "Bond", "risco": risco, "venc": venc,
                             "emiss": num(emiss), "devedor": dev, "setor": setor, "fin": trip[-1][0], "aloc": trip[-1][1], "fundos": per})
    return {"data": data, "pl": pl, "rows": rows}

if __name__ == '__main__':
    r = parse(load(sys.argv[1]))
    print(r["data"], r["pl"], len(r["rows"]))
    for x in r["rows"]:
        print(x["ticker"], x["devedor"], x["setor"], x["fin"], x.get("qtd"), x["aloc"], list(x["fundos"]))
