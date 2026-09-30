# Atualiza-o-Fenabrave-e-Anfavea

## Dashboard de cotações B3

Painel em tempo real (estilo card do Google) para MOVI3, SIMH3, VAMO3, JSLG3,
AMOB3, RAPT3, RAPT4, RENT3, FRAS3, ARML3, PRNR3 e TUPY3.

```bash
pip install -r requirements.txt
python dashboard/server.py          # abre http://localhost:8000
python dashboard/server.py --demo   # dados simulados, sem internet
```

- Atualiza as cotações a cada 15 s (fonte: Yahoo Finance, atraso de até 15 min).
- Abre na visão **Todos**: uma grade compacta com o gráfico das 11 ações ao
  mesmo tempo, com um seletor de período (1D, 5D, 1M, 6M, No ano, 1A, 5A)
  que vale para todos.
- Clique numa ação (ou em **Detalhe**) para ver o gráfico 1D / 5D / 1M / 6M / No ano / 1A / 5A,
  abertura, máxima, mínima, fechamento anterior, volume e faixa de 52 semanas.
- Para mudar a lista de ações, edite `TICKERS` em `dashboard/server.py` e em
  `dashboard/index.html`.

## Alerta de ações por e-mail

`alerta_acoes.py` roda pelo workflow **Alerta de ações B3** a cada 2 horas no
pregão (11h, 13h, 15h e 17h, seg a sex). A cada 15 min no pregão ele também
atualiza só a foto de preços do painel, sem e-mail. Se alguma ação estiver com alta ou
queda de **2%, 4% ou 8% ou mais** no dia, envia um e-mail de lembrete usando
os mesmos segredos SMTP do monitor. Também grava `alerts/prices.json`, que
alimenta o painel publicado em https://claude.ai/artifact/UHYqgM4PcixNRmxt7AFBhk.

Para ver o modelo do e-mail sem enviar: `python alerta_acoes.py --demo --dry-run`
(gera `alerts/preview.html`).

## Boletim de notícias materiais

`noticias_acoes.py` roda pelo workflow **Boletim de notícias B3** todo dia às
8h30 e às 18h30 (e-mail) e de hora em hora só para atualizar o painel. Busca no Google News as notícias das 11 empresas, mantém só as
materiais (fato relevante, resultado, M&A, dívida e rating, proventos, gestão,
regulatório, analistas e contratos relevantes), descarta listas genéricas e
conteúdo de "dicas", e envia um e-mail com as novidades desde o último boletim e
um resumo do mercado (Ibovespa, dólar e as ações). Grava `alerts/news.json`,
que alimenta a faixa de notícias do painel.

Prévia sem enviar: `python noticias_acoes.py --dry-run` (gera `alerts/news_preview.html`).

## Debêntures (ANBIMA)

`debentures_anbima.py` roda pelo workflow **Debêntures ANBIMA** nos dias úteis
às 19h30 (e às 8h do dia seguinte, caso o arquivo atrase). Baixa as taxas
indicativas de debêntures da ANBIMA, filtra os papéis dos emissores
acompanhados e guarda o histórico em `alerts/debentures.json`, que alimenta a
aba **Dívida** do painel. Favoritos iniciais: VAMO33, VAMO34 e VAMO19.

Os papéis IPCA+ ganham **NTN-B +** = (1 + taxa) / (1 + NTN-B de referência da
ANBIMA) − 1 e **CDI +** pela inflação implícita e curva prefixada da ETTJ ANBIMA
(aproximação da curva DI). Negócios (quantidade, número de negócios, PU
mínimo/médio/máximo) vêm do SND (debentures.com.br), que também fornece a lista
de todos os papéis registrados dos emissores e o PU da curva dos que não têm
taxa ANBIMA.

## Boletim de crédito

`boletim_credito.py` roda pelo workflow **Boletim de crédito** nos dias úteis às
8h50: atualiza a ANBIMA e envia por e-mail as 5 debêntures que mais fecharam e
as 5 que mais abriram, entre os favoritos e no geral dos emissores.
Prévia: `python boletim_credito.py --dry-run`.

## Alerta de negócios nos favoritos

`alerta_trades.py` roda pelo workflow **Alerta de negócios nos favoritos** a cada
2 horas nos dias úteis (10h15 às 20h15). Consulta os negócios do dia no SND e
envia e-mail quando um favorito (VAMO33, VAMO34, VAMO19) negociou mais de
R$ 1 milhão, com PU médio e taxa média aproximada contra a ANBIMA. Cada papel
e dia é avisado uma vez (de novo se o volume do dia mudar).
