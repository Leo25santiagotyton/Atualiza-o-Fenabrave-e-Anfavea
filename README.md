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
- Clique numa ação para ver o gráfico 1D / 5D / 1M / 6M / No ano / 1A / 5A,
  abertura, máxima, mínima, fechamento anterior, volume e faixa de 52 semanas.
- Para mudar a lista de ações, edite `TICKERS` em `dashboard/server.py` e em
  `dashboard/index.html`.
