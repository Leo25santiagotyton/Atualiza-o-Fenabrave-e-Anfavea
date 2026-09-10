"""Envia um e-mail de teste usando as mesmas credenciais SMTP do monitor,
so para confirmar que o envio esta funcionando."""

from monitor import send_email

send_email(
    subject="[Teste] Monitor ANFAVEA/FENABRAVE",
    body="Se voce recebeu este e-mail, o envio via GitHub Actions esta funcionando certinho!",
)
print("[INFO] E-mail de teste enviado com sucesso.")
