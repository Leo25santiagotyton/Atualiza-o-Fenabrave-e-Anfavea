"""Gera a página do Boletim de Crédito (para publicar como artifact) a partir de alerts/debentures.json.

Uso: python tools/boletim_pagina.py [saída.html]   (padrão: alerts/boletim_credito.html)
Imprime na última linha o assunto do boletim (para a notificação)."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "alerts" / "boletim_credito.html"
r = subprocess.run([sys.executable, "boletim_credito.py", "--dry-run"], cwd=ROOT, capture_output=True, text=True, check=True)
subject = r.stdout.splitlines()[0] if r.stdout else "Boletim de crédito"
html = (ROOT / "alerts" / "credito_preview.html").read_text()
# layout de e-mail (680 px fixos) → página que cabe no celular
html = html.replace('width="680"', 'width="100%"')
html = re.sub(r'(<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" )(?=[^>]*>\s*<tr><td style="padding:2)',
              r'\1style="max-width:680px" ', html)
html = html.replace("white-space:nowrap", "white-space:normal").replace("width:680px", "width:100%")
html = html.replace("<head>", '<head><style>table{max-width:680px}td{word-break:break-word}body{background:#e5e7eb}'
                    '@media(max-width:600px){td{padding-left:6px!important;padding-right:6px!important;font-size:12px!important}}</style>', 1)
html = re.sub(r"<title>.*?</title>", "<title>Boletim de Crédito</title>", html, count=1, flags=re.S)
out.write_text(html)
print(subject)
