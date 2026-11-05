"""Sonda da vitrine pública de seminovos da Turbi: campos de cada carro no payload do Next (RSC)."""
import json
import re
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"}
t = requests.get("https://seminovos.turbi.com.br/seminovos?page=1", headers=UA, timeout=30).text
partes = [json.loads('"' + m + '"') for m in re.findall(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', t)]
flight = "".join(partes)
i = flight.find('"detailsHref"')
a = flight.rfind('{"', 0, flight.rfind('"id"', 0, i) + 1)
print("ITEM0:", flight[max(0, i - 1800):i + 200])
j = flight.find('"total":')
print("\nTOTAL:", flight[j - 300:j + 800])
