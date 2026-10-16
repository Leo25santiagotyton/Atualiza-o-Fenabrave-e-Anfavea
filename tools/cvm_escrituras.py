"""Baixa da CVM (IPE) as escrituras e aditamentos de debêntures de emissores escolhidos e guarda
só os trechos de covenant (índices financeiros e hipóteses de vencimento antecipado).

Uso: python tools/cvm_escrituras.py --emissor "ARMAC" --emissor "RANDON" [--desde 2018] [--diag]
Saída: alerts/escrituras/<emissor>/<data>_<protocolo>.txt (documentos públicos da CVM)
"""
import argparse, csv, io, re, zipfile, datetime, pathlib, unicodedata
import requests
from pypdf import PdfReader

H = {"User-Agent": "Mozilla/5.0 (pesquisa de covenants)"}
IPE = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{}.zip"
OUT = pathlib.Path("alerts/escrituras")
CAT = re.compile(r"escritura|debênture|debenture|securitiza", re.I)
FIN = re.compile(r"d[ií]vida\s+l[ií]quida|ebitda|[ií]ndices?\s+financeiros?|alavancagem|cobertura\s+de\s+juros|patrim[oô]nio\s+l[ií]quido\s+m[ií]nimo", re.I)
RESG = re.compile(r"resgate\s+antecipado\s+facultativo|pr[eê]mio\s+de\s+resgate|pr[eê]mio\s+flat|amortiza[cç][aã]o\s+extraordin[aá]ria\s+facultativa|oferta\s+de\s+resgate", re.I)
OUTROS = re.compile(r"vencimento\s+antecipado\s+(n[aã]o\s+)?autom[aá]tic|cross|inadimpl\w+\s+de\s+qualquer|controle\s+acion[aá]rio|dividendos|classifica[cç][aã]o\s+de\s+risco|raz[aã]o\s+(m[ií]nima\s+)?de\s+garantia", re.I)


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()[:40]


def linhas(ano):
    r = requests.get(IPE.format(ano), headers=H, timeout=300)
    if r.status_code != 200:
        print(f"::notice::IPE {ano}: HTTP {r.status_code}")
        return []
    z = zipfile.ZipFile(io.BytesIO(r.content))
    out = []
    for n in z.namelist():
        out += list(csv.DictReader(io.TextIOWrapper(z.open(n), encoding="latin-1"), delimiter=";"))
    return out


def janelas(txt, re_, raio, lim):
    spans = []
    for m in re_.finditer(txt):
        a, b = max(0, m.start() - raio), min(len(txt), m.end() + raio)
        if spans and a <= spans[-1][1]:
            spans[-1][1] = b
        else:
            spans.append([a, b])
    out, tot = [], 0
    for a, b in spans:
        if tot > lim:
            break
        out.append(txt[a:b]); tot += b - a
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emissor", action="append", required=True, help="regex no nome da companhia")
    ap.add_argument("--desde", type=int, default=2018)
    ap.add_argument("--diag", action="store_true")
    ap.add_argument("--refazer", action="store_true", help="regrava os arquivos já baixados")
    a = ap.parse_args()
    pats = [re.compile(p, re.I) for p in a.emissor]
    docs = []
    for ano in range(a.desde, datetime.date.today().year + 1):
        for l in linhas(ano):
            nome = l.get("Nome_Companhia", "")
            if not any(p.search(nome) for p in pats):
                continue
            tipo = " ".join(l.get(k, "") for k in ("Categoria", "Tipo", "Especie", "Assunto"))
            if a.diag:
                print(f"::notice::{ano} {nome[:30]} | {tipo[:150]}")
            if CAT.search(tipo) and re.search(r"escritura(?!dor|is)|aditamento|termo", tipo, re.I) and not re.search(r"escriturador|mapa ", tipo, re.I):
                docs.append(l)
    print(f"::notice::{len(docs)} documento(s) de escritura/aditamento")
    for l in docs:
        nome = l["Nome_Companhia"]; prot = l.get("Protocolo_Entrega", "") or "x"
        dest = OUT / slug(nome) / f"{l.get('Data_Entrega', '')[:10]}_{prot}.txt"
        if dest.exists() and not a.refazer:
            continue
        try:
            r = requests.get(l["Link_Download"], headers=H, timeout=180)
            pdf = PdfReader(io.BytesIO(r.content))
            txt = re.sub(r"\s+", " ", " ".join((p.extract_text() or "") for p in pdf.pages))
        except Exception as e:
            print(f"::notice::falha {nome} {prot}: {e}")
            continue
        fin = janelas(txt, FIN, 900, 14000)
        out = janelas(txt, OUTROS, 350, 6000)
        res = janelas(txt, RESG, 1200, 12000)
        dest.parent.mkdir(parents=True, exist_ok=True)
        cab = (f"# {nome} | {l.get('Assunto', '')} | {l.get('Tipo', '')} {l.get('Especie', '')}\n"
               f"# entregue {l.get('Data_Entrega', '')} | referência {l.get('Data_Referencia', '')} | {l['Link_Download']}\n"
               f"# {len(pdf.pages)} páginas, {len(txt)} caracteres de texto{' (provavelmente digitalizado, sem texto)' if len(txt) < 2000 else ''}\n")
        dest.write_text(cab + "\n## ÍNDICES FINANCEIROS\n" + "\n…\n".join(fin) + "\n\n## OUTROS GATILHOS\n" + "\n…\n".join(out) + "\n\n## RESGATE ANTECIPADO\n" + "\n…\n".join(res) + "\n", encoding="utf-8")
        print(f"::notice::ok {dest} fin={len(fin)} out={len(out)}")


if __name__ == "__main__":
    main()
