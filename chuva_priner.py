"""
Chuva × Priner
--------------
A Priner (PRNR3) trabalha em boa parte a céu aberto (andaimes, pintura, isolamento, montagem e mineração), e a
própria empresa associa a produtividade às chuvas. Este script junta:

- previsão diária (Open-Meteo, "best match") numa grade de 1° sobre o Brasil: 7 dias anteriores + 16 à frente;
- a mesma previsão, com a probabilidade de chuva, em cada ponto da Priner (dados/priner_sites.json: filiais e
  operações em clientes, com relevância 1 a 3 e a fonte de cada uma);
- visão MENSAL por ponto: histórico desde 2016 pela reanálise ERA5 (archive-api), normal de cada mês (média
  2016-2025), mês corrente = realizado até ontem + previsão até o fim do mês, e os próximos meses pela previsão
  sazonal do ECMWF (SEAS5, média do ensemble e anomalia contra a climatologia do próprio modelo);
- o contorno simplificado dos estados (dados/br_ufs.json) para o mapa.

Grava alerts/chuva_priner.json → banco do painel (debentures/chuva), aba Monitoramento › CHUVA · PRINER.
O histórico mensal fica em cache em alerts/chuva_mensal_cache.json (só os últimos meses são baixados de novo).
"""

import calendar
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent
OUT = ROOT / "alerts" / "chuva_priner.json"
CACHE = ROOT / "alerts" / "chuva_mensal_cache.json"
UFS = ROOT / "dados" / "br_ufs.json"
SITES = ROOT / "dados" / "priner_sites.json"
API = "https://api.open-meteo.com/v1/forecast"
ARQ = "https://archive-api.open-meteo.com/v1/archive"
SAZ = "https://seasonal-api.open-meteo.com/v1/seasonal"
BRT = timezone(timedelta(hours=-3))
PASSADO, FUTURO = 7, 16
PASSO = 1.0  # graus
HIST_INI = 2016
NORMAL_ANOS = range(2016, 2026)
MESES_PAINEL = 36  # meses de histórico mandados ao painel


def dentro(lon, lat, aneis):
    ok = False
    for r in aneis:
        j = len(r) - 1
        for i in range(len(r)):
            xi, yi = r[i]
            xj, yj = r[j]
            if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                ok = not ok
            j = i
    return ok


def grade(ufs):
    aneis = [r for u in ufs for r in u["aneis"]]
    pts = []
    lat = 5.0
    while lat >= -33.5:
        lon = -73.5
        while lon <= -34.5:
            if dentro(lon, lat, aneis):
                pts.append((round(lat, 2), round(lon, 2)))
            lon += PASSO
        lat -= PASSO
    return pts


def _get(url, params, lote_desc):
    for tent in range(4):
        try:
            r = requests.get(url, params=params, timeout=180)
            r.raise_for_status()
            js = r.json()
            return js if isinstance(js, list) else [js]
        except Exception as exc:  # noqa: BLE001
            if tent == 3:
                raise
            print(f"[AVISO] {lote_desc}: {exc}; tentando de novo")
            time.sleep(10 * (tent + 1))


def consulta(url, coords, base, n=100, desc="Open-Meteo"):
    """Open-Meteo aceita várias coordenadas numa chamada; devolve lista na mesma ordem."""
    out = []
    for i in range(0, len(coords), n):
        lote = coords[i:i + n]
        params = {"latitude": ",".join(f"{a}" for a, _ in lote), "longitude": ",".join(f"{b}" for _, b in lote),
                  "timezone": "America/Sao_Paulo", **base}
        out.extend(_get(url, params, f"{desc} lote {i}"))
        time.sleep(1)
    return out


def _ym(d):
    return d[:7]


def mensal(sites, prev_sites):
    """Soma mensal por ponto: histórico ERA5 (com cache), normal, mês corrente (realizado + previsão) e sazonal."""
    hoje = datetime.now(BRT).date()
    fim_arq = hoje - timedelta(days=6)  # a reanálise sai com ~5 dias de atraso
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    hist = {}
    novos, velhos = [], []
    for s in sites:
        k = f"{s['lat']},{s['lon']}"
        (velhos if k in cache else novos).append(s)
    def baixa(lista, ini):
        if not lista:
            return
        js = consulta(ARQ, [(s["lat"], s["lon"]) for s in lista],
                      {"start_date": ini, "end_date": fim_arq.isoformat(), "daily": "precipitation_sum"}, n=5, desc="ERA5")
        for s, d in zip(lista, js):
            k = f"{s['lat']},{s['lon']}"
            m = dict(cache.get(k, {}))
            soma, dias = {}, {}
            for t, v in zip(d["daily"]["time"], d["daily"]["precipitation_sum"]):
                if v is None:
                    continue
                soma[_ym(t)] = soma.get(_ym(t), 0) + v
                dias[_ym(t)] = dias.get(_ym(t), 0) + 1
            for ym, v in soma.items():
                m[ym] = [round(v, 1), dias[ym]]
            cache[k] = m
    baixa(novos, f"{HIST_INI}-01-01")
    # os já em cache: refaz só os últimos ~3 meses (a reanálise preliminar pode ser revista)
    baixa(velhos, (hoje.replace(day=1) - timedelta(days=75)).replace(day=1).isoformat())
    CACHE.write_text(json.dumps(cache, separators=(",", ":")), encoding="utf-8")
    print(f"[INFO] ERA5: {len(novos)} pontos novos (desde {HIST_INI}), {len(velhos)} atualizados; até {fim_arq}")

    ym_hoje = hoje.strftime("%Y-%m")
    n_dias_mes = calendar.monthrange(hoje.year, hoje.month)[1]
    # sazonal (SEAS5): média do ensemble e anomalia, mês a mês
    saz = consulta(SAZ, [(s["lat"], s["lon"]) for s in sites], {"monthly": "precipitation_mean,precipitation_anomaly"}, n=50, desc="SEAS5")
    out_sites = []
    meses_hist = []
    y, m = hoje.year, hoje.month
    for _ in range(MESES_PAINEL):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        meses_hist.append(f"{y}-{m:02d}")
    meses_hist.reverse()
    for s, sz, pv in zip(sites, saz, prev_sites):
        c = cache.get(f"{s['lat']},{s['lon']}", {})
        normal = []
        for mes in range(1, 13):
            vals = [c[f"{a}-{mes:02d}"][0] for a in NORMAL_ANOS if f"{a}-{mes:02d}" in c and c[f"{a}-{mes:02d}"][1] >= 28]
            normal.append(round(sum(vals) / len(vals), 1) if vals else None)
        hist = [(c.get(ym) or [None, 0])[0] if (c.get(ym) or [None, 0])[1] >= 28 else None for ym in meses_hist]
        # mês corrente: ERA5 até fim_arq + diária do forecast (past_days) para o resto do realizado + previsão até o fim
        real = 0.0
        dias_ok = set()
        if ym_hoje in c and fim_arq.strftime("%Y-%m") == ym_hoje:
            real = c[ym_hoje][0]
            dias_ok = {date(hoje.year, hoje.month, d).isoformat() for d in range(1, fim_arq.day + 1)}
        prev = 0.0
        for t, v in zip(pv["dias"], pv["mm"]):
            if not t.startswith(ym_hoje) or t in dias_ok or v is None:
                continue
            if t < hoje.isoformat():
                real += v
            else:
                prev += v
        ult_prev = max([t for t in pv["dias"] if t.startswith(ym_hoje)] or [hoje.isoformat()])
        sm = sz.get("monthly", {})
        sazonal = [{"mes": t[:7], "mm": round(mm, 1) if mm is not None else None, "anom": round(an, 1) if an is not None else None}
                   for t, mm, an in zip(sm.get("time", []), sm.get("precipitation_mean", []), sm.get("precipitation_anomaly", []))
                   if t[:7] >= ym_hoje]
        out_sites.append({"hist": hist, "normal": normal, "atual": {"mes": ym_hoje, "realizado": round(real, 1), "previsto": round(prev, 1),
                                                                     "ate": ult_prev, "dias_mes": n_dias_mes}, "sazonal": sazonal})
    return {"meses": meses_hist, "normal_anos": f"{NORMAL_ANOS[0]}–{NORMAL_ANOS[-1]}", "era5_ate": fim_arq.isoformat(), "sites": out_sites,
            "fonte": "Histórico: reanálise ERA5 (Copernicus/ECMWF) via Open-Meteo; normal = média " + f"{NORMAL_ANOS[0]}–{NORMAL_ANOS[-1]}"
                     + "; próximos meses: previsão sazonal ECMWF SEAS5 (média do ensemble) via Open-Meteo."}


def main():
    ufs = json.loads(UFS.read_text(encoding="utf-8"))
    base_sites = json.loads(SITES.read_text(encoding="utf-8"))
    pts = grade(ufs)
    print(f"[INFO] grade de {PASSO}°: {len(pts)} pontos dentro do Brasil")
    diaria = {"daily": "precipitation_sum", "past_days": PASSADO, "forecast_days": FUTURO}
    g = consulta(API, pts, diaria)
    dias = g[0]["daily"]["time"]
    hoje = datetime.now(BRT).strftime("%Y-%m-%d")
    grid = [[lat, lon, [None if v is None else round(v, 1) for v in d["daily"]["precipitation_sum"]]]
            for (lat, lon), d in zip(pts, g)]
    s = consulta(API, [(x["lat"], x["lon"]) for x in base_sites], {**diaria, "daily": "precipitation_sum,precipitation_probability_max"})
    sites = []
    for x, d in zip(base_sites, s):
        dd = d["daily"]
        sites.append({**x, "peso": x.get("relevancia", 1),
                      "mm": [None if v is None else round(v, 1) for v in dd["precipitation_sum"]],
                      "prob": dd.get("precipitation_probability_max")})
    try:
        mens = mensal(base_sites, [{"dias": dias, "mm": x["mm"]} for x in sites])
    except Exception as exc:  # noqa: BLE001
        print(f"[AVISO] visão mensal não atualizada: {exc}")
        old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
        mens = old.get("mensal")
        if mens and len(mens.get("sites", [])) != len(sites):
            mens = None
    out = {"updatedAt": datetime.now(BRT).isoformat(timespec="seconds"), "gerado_em": datetime.now(BRT).strftime("%d/%m/%Y %H:%M"),
           "fonte": "Open-Meteo (best match: ECMWF/GFS/ICON e modelos regionais)", "hoje": hoje, "dias": dias,
           "passo": PASSO, "grade": grid, "sites": sites, "ufs": ufs, "mensal": mens,
           "fontes_sites": {"site": "https://www.priner.com.br/contato/", "cnpj": "Cadastro de filiais do CNPJ 18.593.815"}}
    OUT.parent.mkdir(exist_ok=True)
    txt = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    OUT.write_text(txt, encoding="utf-8")
    print(f"[INFO] {len(sites)} pontos da Priner; {len(dias)} dias ({dias[0]} a {dias[-1]}); {len(txt) // 1024} KB")
    if len(txt) > 250_000:
        print("[ERRO] arquivo passa de 250 KB (limite do banco do painel)", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
