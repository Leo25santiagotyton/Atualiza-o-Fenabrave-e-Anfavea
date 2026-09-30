"""Envia um e-mail de TESTE do aviso de nova emissão, usando dois papéis reais como exemplo."""

import json
from pathlib import Path

import requests

import debentures_anbima as d
from negocios_snd import fetch_agenda, fetch_details
from alerta_acoes import send_email

data = json.loads((Path(__file__).resolve().parent.parent / "alerts" / "debentures.json").read_text())
papers = {p["code"]: p for p in data["papers"]}
codes = [c for c in ("VAMO34", "PRNR14") if c in papers] or list(papers)[:2]

# reaproveita o modelo real, só troca o assunto
orig = d.send_email
d.send_email = lambda subject, text, html: send_email("[TESTE] " + subject, "[TESTE — exemplo com papéis já existentes]\n" + text, html)
s = requests.Session()
s.headers.update(d.HEADERS)
for c in codes:  # ficha e agenda na hora, caso o arquivo ainda não tenha
    try:
        papers[c]["details"] = papers[c].get("details") if papers[c].get("detailsV") == 2 else fetch_details(s, c)
        papers[c]["agenda"] = papers[c].get("agenda") or fetch_agenda(s, c)
    except Exception as e:
        print(f"[AVISO] {c}: {e}")
    print(c, papers[c].get("details"), (papers[c].get("agenda") or [])[:6])
d.send_new_issues(codes, papers, s)
d.send_email = orig
