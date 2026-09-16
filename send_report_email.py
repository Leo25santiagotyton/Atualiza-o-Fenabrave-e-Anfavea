"""Envia um e-mail de relatório (assunto/corpo definidos em tempo de execução)
usando as mesmas credenciais SMTP do monitor. Usado pelo workflow
`report-email.yml`, disparado pelas rotinas semanal/mensal do pipeline.

Variáveis de ambiente esperadas (além das já usadas por monitor.py):
  REPORT_SUBJECT   assunto do e-mail
  REPORT_BODY_B64  corpo do e-mail (texto simples), em base64 UTF-8
"""

import base64
import os

from monitor import send_email

subject = os.environ["REPORT_SUBJECT"]
body = base64.b64decode(os.environ["REPORT_BODY_B64"]).decode("utf-8")

send_email(subject=subject, body=body)
print("[INFO] Relatório enviado por e-mail.")
