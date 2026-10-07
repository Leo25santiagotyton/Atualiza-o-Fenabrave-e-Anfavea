"""Sonda temporária: texto do release ANFAVEA outubro/2026 (dados de setembro)."""
import io, requests, pdfplumber
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
for u, n, lim in [("https://anfavea.com.br/site/wp-content/uploads/2026/10/RELEASE-OUTUBRO26-1.pdf", 6, 6000),
                  ("https://anfavea.com.br/site/wp-content/uploads/2026/10/Coletiva-de-Imprensa-Outubro.pdf", 40, 1500)]:
    pr = requests.get(u, headers=H, timeout=90); print("PDF", pr.status_code, len(pr.content), u)
    with pdfplumber.open(io.BytesIO(pr.content)) as p:
        print("paginas", len(p.pages))
        for i, pg in enumerate(p.pages[:n]):
            print(f"--- p{i+1}"); print((pg.extract_text() or "")[:lim])
