"""
Negócio a negócio de renda fixa (debêntures, CRA, CRI) no Boletim Diário do Mercado da B3
-----------------------------------------------------------------------------------------
Tabela "Trade" do BDI (arquivos.b3.com.br/bdi, grupo Renda fixa). A página chama:
  POST https://arquivos.b3.com.br/bdi/table/Trade/{data}/{data}/{página}/{por página}   corpo {}
e recebe {"table": {"columns": [...], "values": [[...], ...], "pageCount": N}}.

Colunas (ordem da B3): data, data, instrumento (DEB/CRA/CRI/...), emissor, código IF, quantidade,
preço, volume (R$), taxa, origem, horário, data, id do negócio, ISIN, liquidação, situação, idSer.
Para CRA/CRI o "emissor" é a securitizadora; por isso o filtro é pelo código IF.
"""

import time

URL = "https://arquivos.b3.com.br/bdi/table/Trade/{d}/{d}/{page}/{take}"
HEADERS = {"Accept": "application/json, text/plain, */*", "Content-Type": "application/json",
           "Referer": "https://arquivos.b3.com.br/bdi/tabelas?lang=pt-BR", "Origin": "https://arquivos.b3.com.br"}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_bdi_trades(session, d, codes, take=500, max_pages=400):
    """{código: [[iso, hora, qtd, preço, volume, taxa, origem, situação, instrumento, id]]} do dia `d` para os códigos pedidos.
    Devolve None se a B3 não tiver a tabela do dia."""
    codes = {c.upper() for c in codes}
    out, page, pages, total, seen = {}, 1, None, 0, set()
    while True:
        r = session.post(URL.format(d=d.isoformat(), page=page, take=take), json={}, headers=HEADERS, timeout=90)
        if r.status_code != 200:
            print(f"[AVISO] BDI Trade {d} pág. {page}: status {r.status_code}")
            break
        t = (r.json() or {}).get("table") or {}
        vals = t.get("values") or []
        if pages is None:
            pages = t.get("pageCount") or 1
            if not vals:
                return None
        total += len(vals)
        for v in vals:
            if len(v) < 16:
                continue
            code = str(v[4] or "").strip().upper()
            if code not in codes or (v[12] and v[12] in seen):
                continue
            seen.add(v[12])
            out.setdefault(code, []).append([d.isoformat(), str(v[10] or "")[:8], _num(v[5]), _num(v[6]), _num(v[7]), _num(v[8]),
                                             str(v[9] or "")[:40], str(v[15] or "")[:20], str(v[2] or ""), str(v[12] or "")])
        page += 1
        if page > pages or page > max_pages or not vals:
            break
        time.sleep(0.2)
    print(f"[INFO] BDI {d}: {total} negócios de renda fixa lidos ({pages} pág.), {sum(len(x) for x in out.values())} dos papéis acompanhados")
    return out
