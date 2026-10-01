"""Uso: na pasta com valores.tsv e hist.tsv, `python3 tools/bonds_build.py "dd/mm/aaaa hh:mm"` → bonds.json.
Monta o documento debentures/bonds a partir das abas 'Monitor valores' e 'Histórico' (TSV) da planilha Monitor_Bonds_Resumido_BDP."""
import json, sys
from datetime import datetime
updated = sys.argv[1]  # ex.: "01/10/2026 13:30"
def num(s):
    s = (s or "").strip().replace("+", "")
    if not s or s.startswith("#") or s == "N/D": return None
    try: return float(s.replace(".", "").replace(",", "."))
    except ValueError: return None
def mat(s):
    try: return datetime.strptime(s.strip(), "%d-%b-%y").date().isoformat()
    except ValueError: return None
bonds = []
for line in open("valores.tsv", encoding="utf-8"):
    c = line.rstrip("\n").split("\t")
    if len(c) < 23 or not c[3].strip(): continue
    m = mat(c[19]); cpn = num(c[18])
    label = c[2].strip() or (f"{cpn:.2f}%".replace(".", ",") + (f" {m[5:7]}/{m[:4]}" if m else ""))
    bonds.append({"issuer": c[0].strip(), "country": c[1].strip(), "bond": label, "isin": c[3].strip(),
                  "px": num(c[4]), "pxD1": num(c[5]), "dPx": num(c[6]), "ytm": num(c[7]), "ytmD1": num(c[8]), "d1": num(c[9]),
                  "ytm1w": num(c[10]), "d1w": num(c[11]), "ytm1m": num(c[12]), "d1m": num(c[13]), "ytmOpen": num(c[14]), "dOpen": num(c[15]),
                  "dur": num(c[16]), "zspr": num(c[17]), "cpn": cpn, "maturity": m, "amt": num(c[20]),
                  "rating": None if c[21].startswith("#") else c[21].strip(), "lastUpdate": c[22].strip()})
hist = {}
for line in open("hist.tsv", encoding="utf-8"):
    c = line.rstrip("\n").split("\t")
    d, isin, px, y = c[:4]
    vol = num(c[4]) if len(c) > 4 else None  # volume (TRACE), se a planilha trouxer
    dd, mm, yy = d.split("/")
    row = [f"{yy}-{mm}-{dd}", round(num(px), 3), round(num(y), 3)]
    if vol is not None:
        row.append(vol)
    hist.setdefault(isin, []).append(row)
doc = {"updatedAt": datetime.strptime(updated, "%d/%m/%Y %H:%M").strftime("%Y-%m-%dT%H:%M:00-03:00"), "updatedLabel": updated,
       "source": "Planilha Monitor_Bonds_Resumido_BDP (Bloomberg BDP/BDH) · SharePoint Tyton", "bonds": bonds, "history": hist}
json.dump(doc, open("bonds.json", "w"), ensure_ascii=False)
print(len(bonds), {k: len(v) for k, v in hist.items()})
