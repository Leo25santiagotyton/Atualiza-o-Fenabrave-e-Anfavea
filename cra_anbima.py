"""
CRI/CRA pela API oficial da ANBIMA (Preços e Índices – mercado secundário de CRI e CRA)
--------------------------------------------------------------------------------------
O portal data.anbima.com.br protege a API dele com reCAPTCHA, então aqui usamos a API
oficial da ANBIMA (developers.anbima.com.br), que exige cadastro gratuito e credenciais:

  ANBIMA_CLIENT_ID, ANBIMA_CLIENT_SECRET   (secrets do GitHub)
  ANBIMA_API_BASE                          (opcional; padrão produção, ou https://api-sandbox.anbima.com.br)

Os CRAs são ligados ao grupo pelo DEVEDOR (originador do crédito), não pelo emissor, que é a
securitizadora. Sem credenciais, o módulo não faz nada.
"""

import base64
import os
import unicodedata
from datetime import date, datetime

AUTH_PATH = "/oauth/access-token"
FEED_PATH = "/feed/precos-indices/v1/cri-cra/mercado-secundario"


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).upper().strip()


def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(".", "").replace(",", ".")) if "," in str(v) else float(v)
    except ValueError:
        return None


def _first(rec, *keys):
    for k in keys:
        if rec.get(k) not in (None, ""):
            return rec[k]
    return None


def enabled():
    return bool(os.environ.get("ANBIMA_CLIENT_ID") and os.environ.get("ANBIMA_CLIENT_SECRET"))


class Api:
    def __init__(self, session):
        self.s = session
        self.base = (os.environ.get("ANBIMA_API_BASE") or "https://api.anbima.com.br").rstrip("/")
        self.cid = os.environ["ANBIMA_CLIENT_ID"]
        self.secret = os.environ["ANBIMA_CLIENT_SECRET"]
        self.token = None

    def _auth(self):
        basic = base64.b64encode(f"{self.cid}:{self.secret}".encode()).decode()
        r = self.s.post(self.base + AUTH_PATH, json={"grant_type": "client_credentials"},
                        headers={"Authorization": f"Basic {basic}", "Content-Type": "application/json"}, timeout=30)
        r.raise_for_status()
        self.token = r.json()["access_token"]

    def get(self, path, params):
        if not self.token:
            self._auth()
        for _ in range(2):
            r = self.s.get(self.base + path, params=params, timeout=60,
                           headers={"client_id": self.cid, "access_token": self.token, "Accept": "application/json"})
            if r.status_code == 401:
                self._auth()
                continue
            return r
        return r


def _date_br(v):
    if not v:
        return ""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(v)[:19] if "T" in str(v) else str(v)[:10], fmt).strftime("%d/%m/%Y")
        except ValueError:
            pass
    return str(v)


def _index(rec):
    tipo = _norm(_first(rec, "tipo_remuneracao", "indexador", "indice", "taxa_correcao") or "")
    if "IPCA" in tipo:
        return "IPCA +"
    if "DI" in tipo and ("%" in tipo or "PERCENT" in tipo):
        return "% DI"
    if "DI" in tipo:
        return "DI +"
    return tipo.title() or ""


def fetch_cras(session, d):
    """[{code, name, devedor, maturity, index, section, rate, pu, duration(du), ntnbRef, ...}] do dia, ou None."""
    api = Api(session)
    r = api.get(FEED_PATH, {"data": d.isoformat()})
    if r.status_code in (204, 404):
        return None
    r.raise_for_status()
    data = r.json()
    recs = data if isinstance(data, list) else (data.get("content") or data.get("data") or data.get("items") or [])
    if not recs:
        return None
    if not fetch_cras.logged:
        fetch_cras.logged = True
        print(f"[INFO] CRI/CRA ANBIMA {d}: {len(recs)} registros; campos: {sorted(recs[0].keys())}")
    out = []
    for rec in recs:
        code = _first(rec, "codigo_ativo", "codigo", "ativo")
        if not code:
            continue
        kind = _norm(_first(rec, "tipo_contrato", "tipo") or ("CRA" if str(code).upper().startswith("CRA") else "CRI"))
        devedor = _first(rec, "originador_credito", "devedor", "originador", "cedente") or ""
        dur = _num(_first(rec, "duration"))
        out.append({
            "code": str(code).upper(),
            "kind": "CRA" if "CRA" in kind else "CRI",
            "name": devedor or _first(rec, "emissor") or "",
            "devedor": devedor,
            "securitizadora": _first(rec, "emissor", "securitizadora") or "",
            "serie": _first(rec, "serie"),
            "emissao": _first(rec, "emissao"),
            "maturity": _date_br(_first(rec, "data_vencimento", "vencimento")),
            "index": _index(rec),
            "section": "CRA" if "CRA" in kind else "CRI",
            "rate": _num(_first(rec, "taxa_indicativa")),
            "rateMin": _num(_first(rec, "taxa_compra", "intervalo_min")),
            "rateMax": _num(_first(rec, "taxa_venda", "intervalo_max")),
            "pu": _num(_first(rec, "pu", "vl_pu", "pu_indicativo")),
            "duration": dur,
            "ntnbRef": _date_br(_first(rec, "referencia_ntnb")),
        })
    return out


fetch_cras.logged = False


def matches(row, group_of):
    """Liga o CRA/CRI ao grupo pelo devedor (e, na falta, pelo nome da série)."""
    for name in (row.get("devedor"), row.get("name")):
        if name:
            t, label = group_of({"name": name})
            if t:
                return t, label
    return None, None


if __name__ == "__main__":
    import requests

    if not enabled():
        print("Defina ANBIMA_CLIENT_ID e ANBIMA_CLIENT_SECRET.")
    else:
        rows = fetch_cras(requests.Session(), date.today()) or []
        print(len(rows), rows[:3])
