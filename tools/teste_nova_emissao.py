"""Envia um e-mail de TESTE do aviso de nova emissão, usando dois papéis reais como exemplo."""

import json
from pathlib import Path

import debentures_anbima as d
from alerta_acoes import send_email

data = json.loads((Path(__file__).resolve().parent.parent / "alerts" / "debentures.json").read_text())
papers = {p["code"]: p for p in data["papers"]}
codes = [c for c in ("VAMO34", "PRNR14") if c in papers] or list(papers)[:2]

# reaproveita o modelo real, só troca o assunto
orig = d.send_email
d.send_email = lambda subject, text, html: send_email("[TESTE] " + subject, "[TESTE — exemplo com papéis já existentes]\n" + text, html)
d.send_new_issues(codes, papers)
d.send_email = orig
