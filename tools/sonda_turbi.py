"""Sonda de caminhões seminovos: JSON-LD e cartões da Vamos; vehicles.json da VolksConfia; config da SelecTrucks."""
import json
import re
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
      "Accept-Language": "pt-BR,pt;q=0.9"}
s = requests.Session()
s.headers.update(UA)

print("##### VAMOS")
p1 = s.get("https://vamos.com.br/seminovos", timeout=40).text
p2 = s.get("https://vamos.com.br/seminovos?page=2", timeout=40).text
i1 = list(dict.fromkeys(re.findall(r'/seminovo/([a-z0-9-]+)', p1)))
i2 = list(dict.fromkeys(re.findall(r'/seminovo/([a-z0-9-]+)', p2)))
print("p1", len(i1), i1[:3], "p2", len(i2), i2[:3], "iguais?", i1 == i2)
for ld in re.findall(r'<script type="application/ld\+json">(.*?)</script>', p1, re.S)[:4]:
    print("LD:", ld[:1500])
k = p1.find('/seminovo/' + i1[0])
print("CARD:", re.sub(r"\s+", " ", p1[k - 200:k + 2500]))
for pat in [r'data-mlc-est-[a-z-]+', r'page=', r'data-page', r'api/[a-z/]+', r'/_next/data', r'fetch\(']:
    print(pat, sorted(set(re.findall(pat, p1)))[:15])

print("\n##### VOLKSCONFIA")
r = s.get("https://volksconfia.com.br/vehicles.json", timeout=40)
print(r.status_code, len(r.text))
try:
    j = r.json()
    lst = j if isinstance(j, list) else next((v for v in j.values() if isinstance(v, list)), [])
    print(type(j).__name__, (list(j)[:10] if isinstance(j, dict) else len(j)), "itens", len(lst))
    print(json.dumps(lst[:2], ensure_ascii=False)[:2500])
except Exception as e:
    print("nao json", e, r.text[:500])

print("\n##### SELECTRUCKS")
t = s.get("https://www.selectrucks.com.br/caminhao-seminovos-usados/concessionaria-selectrucks", timeout=40).text
for pat in [r'siteId\s*=\s*[^;\n]+', r'"siteId"\s*:\s*"[^"]+"', r'token\s*[:=]\s*[^,;\n]{0,80}', r'data\.config\s*=\s*', r'"token"\s*:\s*"[^"]+"']:
    print(pat, re.findall(pat, t)[:5])
i = t.find('"token"')
print(repr(t[max(0, i - 800):i + 800]))
