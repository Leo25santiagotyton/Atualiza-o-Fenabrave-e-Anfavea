"""Sonda temporária: trechos dos releases 2T26 de Randoncorp e Tupy sobre América do Norte."""
import io, re, requests, pdfplumber
DOCS = {
 "RANDON": "https://api.mziq.com/mzfilemanager/v2/d/a8409c46-1419-4694-b935-b868e0b64e35/cba9750b-4418-1060-0a74-124acb3f218c?origin=2",
 "TUPY": "https://api.mziq.com/mzfilemanager/v2/d/5ab6a371-dd2f-452a-b6b2-22c97ed0abbb/7d05dc0c-683b-8fa5-e402-445069d76318?origin=2",
}
PAT = re.compile(r"am[ée]rica do norte|north america|estados unidos|eua\b|nafta|class[e]? 8|mercado externo|exporta|receita (l[ií]quida )?por|ve[ií]culos comerciais|pesad|%", re.I)
for k, u in DOCS.items():
    r = requests.get(u, timeout=60, headers={"User-Agent": "curl/8.5.0"})
    print("=====", k, r.status_code, len(r.content))
    PAGS = {"RANDON": [4, 8], "TUPY": [2, 3, 5]}[k]
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        for n in PAGS:
            print(f"--- p{n}"); print(pdf.pages[n - 1].extract_text())
