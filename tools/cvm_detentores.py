"""Quem mais carrega as debêntures/CRAs/bonds acompanhados no painel.

Fonte: CVM, Composição e Diversificação das Aplicações (CDA) dos fundos, mensal
(https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/), mais o cadastro de fundos para o gestor.
Lê os dois meses mais recentes, procura os códigos de todos os papéis do painel
(alerts/debentures_painel.json) e os ISINs dos bonds (alerts/bonds.json) e grava
alerts/detentores.json: por papel, os fundos que têm o papel, com gestor, quantidade e valor,
e a quantidade no mês anterior (para ver quem entrou, saiu, aumentou ou reduziu).

Uso: python tools/cvm_detentores.py [--meses 2] [--diag]
"""
import csv, io, json, re, sys, zipfile, datetime
import requests

BASE = "https://dados.cvm.gov.br/dados/FI/"
H = {"User-Agent": "Mozilla/5.0 (painel-b3)"}
OUT = "alerts/detentores.json"
DIAG = "--diag" in sys.argv
csv.field_size_limit(10 ** 8)


def get(url, **kw):
    r = requests.get(url, headers=H, timeout=600, **kw)
    r.raise_for_status()
    return r


def alvos():
    papers = json.load(open("alerts/debentures_painel.json", encoding="utf-8"))["papers"]
    t = {p["code"].upper(): {"code": p["code"], "issuer": p.get("issuer")} for p in papers}
    try:
        for b in json.load(open("alerts/bonds.json", encoding="utf-8")).get("bonds", []):
            if b.get("isin"):
                t[b["isin"].upper()] = {"code": b["isin"], "issuer": b.get("issuer")}
    except FileNotFoundError:
        pass
    return t


def meses_cda(n):
    idx = get(BASE + "DOC/CDA/DADOS/").text
    ms = sorted(set(re.findall(r"cda_fi_(\d{6})\.zip", idx)))
    print("CDA disponíveis:", ms[-6:])
    return ms[-n:]


def num(v):
    v = (v or "").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        try:
            return float(v.replace(".", "").replace(",", "."))
        except ValueError:
            return None


def col(row, *names):
    for n in names:
        for k in row:
            if k and k.upper() == n:
                return row[k]
    return None


def le_cda(ym, tg):
    """Linhas do CDA do mês que citam um dos códigos-alvo (em qualquer coluna)."""
    print(f"baixando cda_fi_{ym}.zip")
    z = zipfile.ZipFile(io.BytesIO(get(BASE + f"DOC/CDA/DADOS/cda_fi_{ym}.zip").content))
    achados = []
    for nm in z.namelist():
        if "BLC" not in nm.upper() and "CONFID" not in nm.upper():
            continue
        with z.open(nm) as f:
            rd = csv.DictReader(io.TextIOWrapper(f, encoding="latin-1", newline=""), delimiter=";")
            if DIAG:
                print("  ", nm, "colunas:", rd.fieldnames)
            n = 0
            for row in rd:
                n += 1
                hit = None
                for k, v in row.items():
                    if not v or k is None:
                        continue
                    u = v.strip().upper()
                    if u in tg:
                        hit = u
                        break
                    if k.upper().startswith("DS_ATIVO") or k.upper() == "DS_ATIVO":
                        for tok in re.findall(r"[A-Z0-9]{6,12}", u):
                            if tok in tg:
                                hit = tok
                                break
                        if hit:
                            break
                if not hit:
                    continue
                achados.append({
                    "alvo": hit, "arq": nm,
                    "cnpj": re.sub(r"\D", "", col(row, "CNPJ_FUNDO_CLASSE", "CNPJ_FUNDO") or ""),
                    "fundo": (col(row, "DENOM_SOCIAL") or "").strip(),
                    "tipo": (col(row, "TP_FUNDO_CLASSE", "TP_FUNDO") or "").strip(),
                    "data": (col(row, "DT_COMPTC") or "").strip(),
                    "qtd": num(col(row, "QT_POS_FINAL")),
                    "vl": num(col(row, "VL_MERC_POS_FINAL")),
                    "aplic": (col(row, "TP_APLIC") or "").strip(),
                    "ativo": (col(row, "TP_ATIVO") or "").strip(),
                })
            if DIAG:
                print("     linhas:", n)
    print(f"  {ym}: {len(achados)} posições nos papéis acompanhados")
    if DIAG:
        for a in achados[:15]:
            print("   ex:", a)
    return achados


def gestores():
    """CNPJ do fundo/classe -> nome do gestor (cadastro novo da Res. 175 e, de reserva, o antigo)."""
    g = {}
    try:
        z = zipfile.ZipFile(io.BytesIO(get(BASE + "CAD/DADOS/registro_fundo_classe.zip").content))
        print("cadastro:", z.namelist())
        fundos = {}
        for nm in z.namelist():
            with z.open(nm) as f:
                rd = csv.DictReader(io.TextIOWrapper(f, encoding="latin-1", newline=""), delimiter=";")
                if DIAG:
                    print("  ", nm, rd.fieldnames)
                rows = list(rd)
            low = nm.lower()
            if "registro_fundo" in low:
                for r in rows:
                    rid = col(r, "ID_REGISTRO_FUNDO")
                    gest = (col(r, "GESTOR") or "").strip()
                    cnpj = re.sub(r"\D", "", col(r, "CNPJ_FUNDO") or "")
                    fundos[rid] = gest
                    if cnpj and gest:
                        g[cnpj] = gest
            elif "registro_classe" in low:
                for r in rows:
                    cnpj = re.sub(r"\D", "", col(r, "CNPJ_CLASSE") or "")
                    rid = col(r, "ID_REGISTRO_FUNDO")
                    if cnpj and fundos.get(rid):
                        g.setdefault(cnpj, fundos[rid])
        # classes lidas antes do arquivo de fundos: segunda passada
        for nm in z.namelist():
            if "registro_classe" in nm.lower():
                with z.open(nm) as f:
                    for r in csv.DictReader(io.TextIOWrapper(f, encoding="latin-1", newline=""), delimiter=";"):
                        cnpj = re.sub(r"\D", "", col(r, "CNPJ_CLASSE") or "")
                        rid = col(r, "ID_REGISTRO_FUNDO")
                        if cnpj and fundos.get(rid):
                            g.setdefault(cnpj, fundos[rid])
    except Exception as e:
        print("cadastro 175 falhou:", e)
    try:
        rd = csv.DictReader(io.StringIO(get(BASE + "CAD/DADOS/cad_fi.csv").content.decode("latin-1")), delimiter=";")
        for r in rd:
            cnpj = re.sub(r"\D", "", col(r, "CNPJ_FUNDO") or "")
            gest = (col(r, "GESTOR") or "").strip()
            if cnpj and gest:
                g.setdefault(cnpj, gest)
    except Exception as e:
        print("cad_fi falhou:", e)
    print("gestores no cadastro:", len(g))
    return g


def curto(n, fundo=True):
    """Encurta nome de fundo/gestor para caber no banco do painel."""
    if fundo:
        n = re.sub(r"\b(FUNDO DE INVESTIMENTO FINANCEIRO|FUNDO DE INVESTIMENTO|DE RESPONSABILIDADE LIMITADA|RESPONSABILIDADE LIMITADA|RESP\.? LIMITADA|RESP LTDA|CRÉDITO PRIVADO|CRED PRIV|CRÉD PRIVADO|CRÉD PRIV|MULTIMERCADO|RENDA FIXA)\b", "", n, flags=re.I)
        lim = 48
    else:
        n = re.sub(r"\b(LTDA\.?|S/?A\.?|S\.A\.|DTVM|GESTÃO DE RECURSOS|GESTAO DE RECURSOS|GESTORA DE RECURSOS|INVESTIMENTOS|ASSET MANAGEMENT|ADMINISTRADORA DE VALORES MOBILIÁRIOS|DISTRIBUIDORA DE TÍTULOS E VALORES MOBILIÁRIOS)\b", "", n, flags=re.I)
        lim = 40
    return re.sub(r"\s+", " ", n).strip(" -.,/")[:lim]


def main():
    n = int(sys.argv[sys.argv.index("--meses") + 1]) if "--meses" in sys.argv else 4
    tg = alvos()
    print("papéis-alvo:", len(tg))
    ms = meses_cda(n)
    pos = {}   # (code, cnpj) -> {ym: [qtd, vl]}
    info = {}
    for ym in ms:
        for a in le_cda(ym, tg):
            k = (tg[a["alvo"]]["code"], a["cnpj"])
            o = pos.setdefault(k, {}).setdefault(ym, [0.0, 0.0])
            o[0] += a["qtd"] or 0
            o[1] += a["vl"] or 0
            info[a["cnpj"]] = a["fundo"]
    gest = gestores()
    idx = {ym: i for i, ym in enumerate(reversed(ms))}   # 0 = mês mais recente
    papeis = {}
    for (code, cnpj), por in pos.items():
        ult = max(por)
        qtd, vl = por[ult]
        if qtd <= 0 and vl <= 0:
            continue
        ant = ms[ms.index(ult) - 1] if ms.index(ult) > 0 else None
        qa = round(por[ant][0]) if ant and ant in por else (0 if ant else None)
        g = curto(gest.get(cnpj, "") or "(gestor não identificado)", False)
        papeis.setdefault(code, {}).setdefault(g, []).append([curto(info[cnpj]), round(qtd), round(vl / 1e3), idx[ult], qa])
    out = {}
    for code, gs in papeis.items():
        out[code] = sorted(([g, sorted(fs, key=lambda f: -f[2])] for g, fs in gs.items()), key=lambda x: -sum(f[2] for f in x[1]))
    doc = {
        "fonte": "CVM · CDA (composição das carteiras dos fundos)",
        "meses": [f"{m[4:]}/{m[:4]}" for m in reversed(ms)],
        "geradoEm": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"),
        "updatedAt": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"),
        "obs": "Por fundo: [nome, quantidade, valor em R$ mil, mês da posição (0 = mais recente em `meses`), quantidade no mês anterior]. Fundos podem pedir sigilo da carteira por até 90 dias; aí a posição mais recente fica de fora e vale a última publicada.",
        "papeis": out,
    }
    s = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    open(OUT, "w", encoding="utf-8").write(s)
    print("gravado", OUT, len(s), "bytes; papéis com detentores:", len(out))


if __name__ == "__main__":
    main()
