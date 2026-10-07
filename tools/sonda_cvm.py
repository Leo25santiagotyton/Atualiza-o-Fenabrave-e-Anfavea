"""Sonda temporária: formas de baixar a série HTRUCKSSAAR do FRED."""
import time, requests
UAS = {"python": None, "curl": "curl/8.5.0",
       "chrome": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
URLS = ["https://fred.stlouisfed.org/graph/fredgraph.csv?id=HTRUCKSSAAR",
        "https://fred.stlouisfed.org/data/HTRUCKSSAAR.txt",
        "https://fred.stlouisfed.org/series/HTRUCKSSAAR",
        "https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=HTRUCKSSAAR"]
for u in URLS:
    for nome, ua in UAS.items():
        t = time.time()
        try:
            r = requests.get(u, headers={"User-Agent": ua} if ua else {}, timeout=60)
            txt = r.text.strip().splitlines()
            print(f"{nome:6} {r.status_code} {time.time()-t:5.1f}s {u}\n   ", txt[:2], txt[-3:] if len(r.text) < 400000 else "")
        except Exception as e:
            print(f"{nome:6} ERRO {time.time()-t:5.1f}s {u} {e}")
