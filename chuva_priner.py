"""
Chuva × Priner
--------------
A Priner (PRNR3) trabalha em boa parte a céu aberto (andaimes, pintura, isolamento, montagem e mineração), e a
própria empresa associa a produtividade às chuvas. Este script junta:

- a previsão de chuva diária da Open-Meteo (modelo "best match", sem chave) numa grade de 1° sobre o Brasil,
  com os 7 dias anteriores (estimativa do modelo) e os próximos 16 dias;
- a mesma previsão, com a probabilidade de chuva, em cada endereço da Priner: filiais do site oficial
  (priner.com.br/contato) e as cidades com filial registrada no CNPJ 18.593.815 (fonte secundária);
- o contorno simplificado dos estados (dados/br_ufs.json) para desenhar o mapa no painel.

Grava alerts/chuva_priner.json → banco do painel (debentures/chuva), aba Monitoramento › CHUVA · PRINER.
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent
OUT = ROOT / "alerts" / "chuva_priner.json"
UFS = ROOT / "dados" / "br_ufs.json"
API = "https://api.open-meteo.com/v1/forecast"
BRT = timezone(timedelta(hours=-3))
PASSADO, FUTURO = 7, 16
PASSO = 1.0  # graus

# peso 2: filial no site oficial da Priner; peso 1: cidade com filial no CNPJ (fonte secundária).
# "polo": o que existe de indústria na região (contexto geográfico, não lista de clientes).
SITES = [
    ("Rio de Janeiro (matriz)", "RJ", -23.00, -43.36, 2, "site", "Sede"),
    ("Macaé", "RJ", -22.37, -41.79, 2, "site", "Base de apoio offshore da Bacia de Campos"),
    ("Duque de Caxias", "RJ", -22.79, -43.31, 1, "cnpj", "Refinaria Duque de Caxias e polo petroquímico"),
    ("Mangaratiba", "RJ", -22.96, -44.04, 1, "cnpj", "Terminal portuário (Itaguaí/Ilha Guaíba)"),
    ("Camaçari", "BA", -12.70, -38.32, 2, "site", "Polo Industrial de Camaçari"),
    ("Candeias", "BA", -12.67, -38.55, 1, "cnpj", "Região da refinaria de Mataripe"),
    ("Salvador", "BA", -12.97, -38.50, 1, "cnpj", "Região metropolitana de Salvador"),
    ("São Paulo", "SP", -23.62, -46.68, 2, "site", "Escritório"),
    ("Barueri", "SP", -23.51, -46.88, 2, "site", "Duas filiais"),
    ("Osasco", "SP", -23.53, -46.79, 1, "cnpj", "Grande São Paulo"),
    ("Mogi das Cruzes", "SP", -23.52, -46.19, 2, "site", "Alto Tietê"),
    ("Piracicaba", "SP", -22.73, -47.65, 2, "site", "Polo industrial de Piracicaba"),
    ("Santa Bárbara d'Oeste", "SP", -22.75, -47.41, 2, "site", "Região de Campinas"),
    ("Sertãozinho", "SP", -21.14, -47.99, 2, "site", "Polo sucroenergético"),
    ("Lençóis Paulista", "SP", -22.60, -48.80, 1, "cnpj", "Celulose e açúcar"),
    ("Belo Horizonte", "MG", -19.92, -43.94, 2, "site", "Quadrilátero Ferrífero"),
    ("Congonhas", "MG", -20.50, -43.86, 1, "cnpj", "Mineração de ferro"),
    ("Serra", "ES", -20.13, -40.31, 1, "cnpj", "Complexo de Tubarão (siderurgia e porto)"),
    ("Maceió", "AL", -9.67, -35.74, 2, "site", "Polo cloroquímico de Alagoas"),
    ("Marechal Deodoro", "AL", -9.71, -35.89, 1, "cnpj", "Polo cloroquímico de Alagoas"),
    ("Jaboatão dos Guararapes", "PE", -8.11, -35.01, 1, "cnpj", "Região de Suape"),
    ("Ribas do Rio Pardo", "MS", -20.44, -53.76, 2, "site", "Celulose (Vale do Rio Pardo)"),
    ("Três Lagoas", "MS", -20.75, -51.68, 1, "cnpj", "Celulose"),
    ("Curitiba", "PR", -25.43, -49.27, 1, "cnpj", "Região metropolitana de Curitiba"),
    ("Rio Grande", "RS", -32.03, -52.10, 1, "cnpj", "Porto e polo naval"),
]


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


def consulta(coords, extra=""):
    """Open-Meteo aceita várias coordenadas numa chamada; devolve lista na mesma ordem."""
    out = []
    for i in range(0, len(coords), 100):
        lote = coords[i:i + 100]
        params = {"latitude": ",".join(f"{a}" for a, _ in lote), "longitude": ",".join(f"{b}" for _, b in lote),
                  "daily": "precipitation_sum" + extra, "past_days": PASSADO, "forecast_days": FUTURO,
                  "timezone": "America/Sao_Paulo"}
        for tent in range(4):
            try:
                r = requests.get(API, params=params, timeout=90)
                r.raise_for_status()
                js = r.json()
                out.extend(js if isinstance(js, list) else [js])
                break
            except Exception as exc:  # noqa: BLE001
                if tent == 3:
                    raise
                print(f"[AVISO] Open-Meteo lote {i}: {exc}; tentando de novo")
                time.sleep(5 * (tent + 1))
        time.sleep(1)
    return out


def main():
    ufs = json.loads(UFS.read_text(encoding="utf-8"))
    pts = grade(ufs)
    print(f"[INFO] grade de {PASSO}°: {len(pts)} pontos dentro do Brasil")
    g = consulta(pts)
    dias = g[0]["daily"]["time"]
    hoje = datetime.now(BRT).strftime("%Y-%m-%d")
    grid = [[lat, lon, [None if v is None else round(v, 1) for v in d["daily"]["precipitation_sum"]]]
            for (lat, lon), d in zip(pts, g)]
    s = consulta([(a, b) for _, _, a, b, *_ in SITES], ",precipitation_probability_max")
    sites = []
    for (nome, uf, lat, lon, peso, fonte, polo), d in zip(SITES, s):
        dd = d["daily"]
        sites.append({"nome": nome, "uf": uf, "lat": lat, "lon": lon, "peso": peso, "fonte": fonte, "polo": polo,
                      "mm": [None if v is None else round(v, 1) for v in dd["precipitation_sum"]],
                      "prob": dd.get("precipitation_probability_max")})
    out = {"updatedAt": datetime.now(BRT).isoformat(timespec="seconds"), "gerado_em": datetime.now(BRT).strftime("%d/%m/%Y %H:%M"),
           "fonte": "Open-Meteo (best match: ECMWF/GFS/ICON e modelos regionais)", "hoje": hoje, "dias": dias,
           "passo": PASSO, "grade": grid, "sites": sites, "ufs": ufs,
           "fontes_sites": {"site": "https://www.priner.com.br/contato/", "cnpj": "Cadastro de filiais do CNPJ 18.593.815"}}
    OUT.parent.mkdir(exist_ok=True)
    txt = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    OUT.write_text(txt, encoding="utf-8")
    print(f"[INFO] {len(sites)} endereços da Priner; {len(dias)} dias ({dias[0]} a {dias[-1]}); {len(txt) // 1024} KB")
    if len(txt) > 250_000:
        print("[ERRO] arquivo passa de 250 KB (limite do banco do painel)", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
