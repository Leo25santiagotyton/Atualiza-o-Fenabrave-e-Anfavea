"""Sonda Vamos: onde estão os cartões além dos 48 primeiros."""
import re
import requests

t = requests.get("https://vamos.com.br/seminovos", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0 Safari/537.36"}, timeout=90).text
pos = [m.start() for m in re.finditer("data-mlc-est-card", t)]
print("total", len(pos), "len", len(t))
for i in (0, 47, 48, 49, 200, 1800, len(pos) - 1):
    if i < len(pos):
        p = pos[i]
        print(f"\n--- #{i} @ {p}:", repr(t[p - 250:p + 350]))
for m in re.finditer(r"<script[^>]*>", t):
    if m.start() > pos[48] if len(pos) > 48 else False:
        print("SCRIPT antes do 49:", t[m.start():m.start() + 120])
        break
