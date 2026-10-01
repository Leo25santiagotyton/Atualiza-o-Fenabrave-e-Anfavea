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

## Swap Dólar + (bonds em US$ → CDI +)

Aba do painel para converter o yield de um bond em dólar em CDI + e pré:

- Curva de cupom cambial limpo da B3 (DOC, formada pelos FRC), cupom sujo (DOL) e juros em US$ (LIB),
  do arquivo TaxaSwap (`curva_b3.py`).
- Ajustes de dólar futuro (DOL) e de FRC do Boletim de Preços da B3 (`b3_derivativos.py`, arquivo PR/BVBG.086).
- Ambos entram na coleta das 8h (`debentures_anbima.py`) e vão para `curveLatest.usd` e `curveLatest.usdMkt`.
- CDI + = ((1 + y)^(dc/360) / (1 + cupom limpo × dc/360))^(252/du) − 1.

## CRI/CRA (por devedor)

`cra_anbima.py` usa a API oficial da ANBIMA (Preços e Índices – CRI/CRA). O portal data.anbima.com.br
protege a API com reCAPTCHA, então é preciso cadastro gratuito em developers.anbima.com.br e os secrets
`ANBIMA_CLIENT_ID` e `ANBIMA_CLIENT_SECRET` (opcional: variável `ANBIMA_API_BASE` para o sandbox).
Os papéis são ligados ao grupo pelo devedor (originador do crédito), não pela securitizadora.

## Nova emissão

O e-mail de nova emissão traz emissão/série, volume (quantidade × valor nominal), remuneração, vencimento e prazo,
bullet ou amortização (agenda do SND) e manchetes recentes sobre o uso dos recursos.

## Atualização do painel

Preços a cada 15 min no pregão (GitHub Actions) e foto de fechamento às 18h05/18h20. O painel sincroniza
por rotinas às :05, :20, :35 e :50 (10h–17h), e às 18h20/18h35 para o fechamento.

## Resumo mensal da Tabela FIPE

`fipe_mensal.py` roda pelo workflow **Resumo FIPE mensal** nos dias 1 a 10 de cada
mês às 8h30 e às 19h. Assim que a FIPE publica a tabela do mês (normalmente no
primeiro dia útil), envia um e-mail com a variação do mês por segmento (hatch,
sedã, SUV, picape, leves no geral, caminhão e moto), o acumulado em 12 meses, a
tabela mês a mês e as maiores altas e quedas. Cada mês é enviado uma vez
(`alerts/fipe_state.json`).

A FIPE não separa por carroceria, então o resumo usa uma cesta fixa de modelos
representativos (lista `CESTA` no script), com até 2 versões e 2 anos-modelo
de cada. A cesta fica em `alerts/fipe_cesta.json` e os preços em
`alerts/fipe_historico.json` (13 meses). A primeira carga leva ~30–60 min;
depois cada mês custa poucas consultas.

Teste: disparo manual do workflow (opção "teste") envia agora com `[Teste]` no assunto.
Prévia sem enviar: `python fipe_mensal.py --demo --dry-run` (gera `alerts/fipe_preview.html`).
