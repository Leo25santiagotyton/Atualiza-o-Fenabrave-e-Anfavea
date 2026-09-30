# Atualiza-o-Fenabrave-e-Anfavea

## Dashboard de cotações B3

Painel em tempo real (estilo card do Google) para MOVI3, SIMH3, VAMO3, JSLG3,
AMOB3, RAPT3, RAPT4, RENT3, FRAS3, ARML3, MILL3 e PRNR3.

```bash
pip install -r requirements.txt
python dashboard/server.py          # abre http://localhost:8000
python dashboard/server.py --demo   # dados simulados, sem internet
```

- Atualiza as cotações a cada 15 s (fonte: Yahoo Finance, atraso de até 15 min).
- Abre na visão **Todos**: uma grade compacta com o gráfico das 12 ações ao
  mesmo tempo, com um seletor de período (1D, 5D, 1M, 6M, No ano, 1A, 5A)
  que vale para todos.
- Clique numa ação (ou em **Detalhe**) para ver o gráfico 1D / 5D / 1M / 6M / No ano / 1A / 5A,
  abertura, máxima, mínima, fechamento anterior, volume e faixa de 52 semanas.
- Para mudar a lista de ações, edite `TICKERS` em `dashboard/server.py` e em
  `dashboard/index.html`.

## Alerta de ações por e-mail

`alerta_acoes.py` roda pelo workflow **Alerta de ações B3** a cada 2 horas no
pregão (11h, 13h, 15h e 17h, seg a sex). Se alguma ação estiver com alta ou
queda de **2%, 4% ou 8% ou mais** no dia, envia um e-mail de lembrete usando
os mesmos segredos SMTP do monitor. Também grava `alerts/prices.json`, que
alimenta o painel publicado em https://claude.ai/artifact/UHYqgM4PcixNRmxt7AFBhk.

Para ver o modelo do e-mail sem enviar: `python alerta_acoes.py --demo --dry-run`
(gera `alerts/preview.html`).
