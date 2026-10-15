"""Sonda: lista no SND (cadastro) e no arquivo diário da ANBIMA os papéis cujo código ou emissor casam com um padrão."""
import re, sys, datetime
import requests
sys.path.insert(0, ".")
from negocios_snd import fetch_registered

PAT = re.compile(sys.argv[1] if len(sys.argv) > 1 else "VOKE|VRENTAL|AGAU", re.I)
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0"
for p in fetch_registered(s):
    if PAT.search(p["code"]) or PAT.search(p["issuer"]):
        print(f"::notice::SND {p['code']} | {p['issuer']} | {p['status']}")
d = datetime.date.today()
for _ in range(7):
    d -= datetime.timedelta(days=1)
    r = s.get(f"https://www.anbima.com.br/informacoes/merc-sec-debentures/arqs/db{d:%y%m%d}.txt", timeout=60)
    if r.status_code == 200 and len(r.content) > 1000:
        for l in r.content.decode("latin-1").splitlines():
            if PAT.search(l):
                print("::notice::ANBIMA " + l[:200])
        break
