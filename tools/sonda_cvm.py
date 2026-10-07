"""Sonda temporária: séries de crédito de veículos (BCB) e relatório B3/Trillia."""
import io, json, re, requests
H = {"User-Agent": "curl/8.5.0"}
def get(u, **k):
    try:
        r = requests.get(u, headers=H, timeout=60, **k); return r
    except Exception as e:
        print("ERRO", u, e)
# 1) catálogo de séries com "veículos"
for q in ["aquisição de veículos", "veiculos concessoes", "veiculos saldo", "financiamento veiculos"]:
    r = get("https://dadosabertos.bcb.gov.br/api/3/action/package_search", params={"q": q, "rows": 60})
    if r is None: continue
    try:
        for p in r.json()["result"]["results"]:
            print("CKAN", p["name"][:110])
    except Exception as e:
        print("ERRO ckan", r.status_code, r.text[:200])
# 2) últimos valores dos candidatos
for n in [20749, 20728, 20673, 20581, 25471, 20652, 20651, 20653, 20554, 20555, 20556, 20627, 20628, 20699, 20700, 20825, 20826]:
    r = get(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{n}/dados/ultimos/3?formato=json")
    print("SGS", n, r.status_code if r is not None else None, (r.text[:160] if r is not None else ""))
# 3) taxas diárias por instituição: modalidades e última janela
base = "https://olinda.bcb.gov.br/olinda/servico/taxaJuros/versao/v2/odata/"
r = get(base + "TaxasJurosDiariaPorInicioPeriodo?$top=20000&$format=json&$orderby=InicioPeriodo%20desc&$select=Segmento,Modalidade,InicioPeriodo,FimPeriodo")
if r is not None:
    try:
        v = r.json()["value"]; print("DIARIA n", len(v), v[0])
        print("MODS", sorted({(x["Segmento"], x["Modalidade"]) for x in v}))
    except Exception as e:
        print("ERRO diaria", r.status_code, r.text[:300])
r = get(base + "TaxasJurosDiariaPorInicioPeriodo?$top=5&$format=json&$orderby=InicioPeriodo%20desc&$filter=Modalidade%20eq%20'Aquisi%C3%A7%C3%A3o%20de%20ve%C3%ADculos%20-%20Pr%C3%A9-fixado'")
print("VEIC", r.status_code if r is not None else None, r.text[:800] if r is not None else "")
# 4) B3/Trillia
for u in ["https://www.b3.com.br/data/files/91/B2/60/30/9B7BE910ADC36BE9AC094EA8/Mercado%20de%20Financiamentos%20de%20Veiculos_mai26.pdf",
          "https://www.b3.com.br/pt_br/noticias/", "https://www.trillia.com.br/", "https://trillia.com.br/"]:
    r = get(u)
    if r is None: continue
    print("B3", r.status_code, len(r.content), u, r.headers.get("content-type"))
    if u.endswith(".pdf") and r.status_code == 200:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(r.content)) as p:
            for i, pg in enumerate(p.pages[:6]):
                print(f"--- p{i+1}"); print("\n".join(l for l in (pg.extract_text() or "").splitlines() if len(l.strip()) > 3)[:1800])
    elif r.status_code == 200:
        for m in set(re.findall(r'href="([^"]*(?:financ|trillia|gravame|veicul)[^"]*)"', r.text, re.I)):
            print("  LINK", m[:160])
