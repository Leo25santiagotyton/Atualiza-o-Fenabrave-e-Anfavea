# Atualiza-o-Fenabrave-e-Anfavea

## Monitor de fontes (ANFAVEA/FENABRAVE/NADA/AutoInnovators)

`monitor.py` roda via GitHub Actions (`.github/workflows/monitor.yml`) e avisa por
e-mail quando as páginas de divulgação de dados dessas fontes mudam.

## Relatórios do Pipeline Crédito Privado

Duas rotinas agendadas do Claude Code disparam o workflow
`.github/workflows/report-email.yml` (via `workflow_dispatch`, com os mesmos
secrets de SMTP do monitor) para enviar por e-mail:

- **Relatório semanal**, no primeiro dia útil de cada semana: quantas novas
  operações surgiram como "Não Iniciado" e "Em análise" na semana que acabou
  de fechar, comparado com a semana anterior.
- **Relatório mensal**, no primeiro dia útil de cada mês: a mesma comparação,
  olhando o mês que acabou de fechar contra o mês anterior.

O "primeiro dia útil" considera fins de semana e os feriados nacionais
brasileiros (`scripts/business_day.py`). Os dados vêm do banco compartilhado
do pipeline (artifact "Pipeline Crédito Privado"), lido por uma sessão do
Claude Code no momento do disparo — por isso essa parte roda como uma rotina
do Claude, e não como um job comum do GitHub Actions.