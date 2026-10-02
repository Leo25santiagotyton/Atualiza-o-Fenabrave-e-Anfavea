"""Sonda: documentos IPE (fatos relevantes/comunicados) na CVM — RAD e dados abertos."""
import csv, io, json, zipfile
import requests

H = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json; charset=utf-8",
     "X-Requested-With": "XMLHttpRequest", "Referer": "https://www.rad.cvm.gov.br/ENET/frmConsultaExternaCVM.aspx"}
s = requests.Session()
try:
    r = s.get("https://www.rad.cvm.gov.br/ENET/frmConsultaExternaCVM.aspx", headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    print("RAD GET", r.status_code, len(r.text))
    body = {"dataDe": "01/10/2026", "dataAte": "02/10/2026", "empresa": "", "setorAtividade": "-1",
            "categoriaEmissor": "-1", "situacaoEmissor": "-1", "tipoParticipante": "-1", "dataReferencia": "",
            "categoria": "IPE_-1_-1_-1", "periodo": "2", "horaIni": "", "horaFim": "", "palavraChave": "",
            "ultimaDtRef": "false", "tipoEmpresa": "0", "token": "", "versaoCaptcha": ""}
    r = s.post("https://www.rad.cvm.gov.br/ENET/frmConsultaExternaCVM.aspx/ListarDocumentos", headers=H,
               data=json.dumps(body), timeout=60)
    print("RAD POST", r.status_code, r.text[:300])
    d = r.json()["d"]
    rows = (d.get("dados") or "").split("&*")
    print("linhas", len(rows))
    for x in rows:
        if "SIMPAR" in x.upper():
            print("SIMPAR>", x[:900])
            break
    print("EX>", rows[0][:900])
except Exception as e:
    print("RAD erro", e)
try:
    r = requests.get("https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_2026.zip", timeout=60)
    print("DA", r.status_code, r.headers.get("Last-Modified"), len(r.content))
    z = zipfile.ZipFile(io.BytesIO(r.content))
    name = z.namelist()[0]
    rd = list(csv.DictReader(io.TextIOWrapper(z.open(name), encoding="latin-1"), delimiter=";"))
    print(name, len(rd), list(rd[0].keys()))
    for x in rd:
        if "SIMPAR" in x.get("Nome_Companhia", "").upper() and x.get("Data_Entrega", "") >= "2026-09-30":
            print(x)
except Exception as e:
    print("DA erro", e)
