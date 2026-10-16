"""Sonda: consulta da FIPE pelo código FIPE (tipoConsulta=codigo) para um carro da Movida.
Uso: python tools/sonda_seminovos.py"""
import json, sys, time
sys.path.insert(0, ".")
from fipe_mensal import Fipe, TIPOS
f = Fipe()
refs = f.referencias()[:3]
print("refs", refs, "calls", f.calls)
for ref, lab in refs[:2]:
    for tc, extra in [("codigo", {}), ("tradicional", {})]:
        for comb in (1, 5):
            d = {"codigoTabelaReferencia": ref, "codigoTipoVeiculo": 1, "anoModelo": 2021, "codigoTipoCombustivel": comb,
                 "tipoVeiculo": "carro", "modeloCodigoExternoFipe": "005490-9", "tipoConsulta": tc}
            time.sleep(1)
            r = f.s.post(f.BASE + "ConsultarValorComTodosParametros", data=d, timeout=20)
            print(lab, tc, comb, r.status_code, r.text[:300])
time.sleep(1)
r = f.s.post(f.BASE + "ConsultarAnoModeloPeloCodigoFipe", data={"codigoTabelaReferencia": refs[0][0], "codigoTipoVeiculo": 1, "modeloCodigoExternoFipe": "005490-9"}, timeout=20)
print("anos pelo código", r.status_code, r.text[:400])
