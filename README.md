# Atualiza-o-Fenabrave-e-Anfavea
## Monitor de notícias - OHI Group

`news_monitor.py` busca notícias novas sobre o **OHI Group** (Omni Helicopters
International) e a **Omni Táxi Aéreo** no Google Notícias (português e inglês)
e envia um e-mail com o título, o veículo, a data e o link de cada matéria.

- Roda a cada 2 horas pelo workflow `.github/workflows/news-ohi.yml` (também dá
  para rodar na mão em *Actions → Monitor de notícias OHI Group → Run workflow*).
- Usa os mesmos secrets de e-mail do monitor ANFAVEA/FENABRAVE.
- Filtro anti-homônimos: aceita "OHI Group", "Omni Táxi Aéreo", "Omni
  Helicopters" etc.; "Omni"/"OHI" sozinhos só contam junto de termos de
  aviação/offshore (helicóptero, Petrobras, H175, táxi aéreo...). Descarta Omni
  Financeira/Banco Omni, operadora Oi, "omnichannel" e similares. Para ajustar,
  edite `STRONG_TERMS`, `CONTEXT_TERMS` e `EXCLUDE_TERMS` no script.
- As notícias já avisadas ficam em `news_state.json`. Na primeira execução só
  são enviadas as notícias das últimas 48h.
