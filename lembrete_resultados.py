"""
Lembrete de divulgação de resultados
------------------------------------
Todo dia às 8h: lê alerts/calendario.json (calendário de RI do painel) e manda um e-mail
quando faltam 14 dias e quando faltam 7 dias para a divulgação de resultados de uma das
empresas acompanhadas (ações e emissores de bonds). Cada aviso sai uma vez só por
empresa, data e marco; se a data mudar (estimada → confirmada), o aviso sai de novo
com a data nova. Os avisos enviados ficam em alerts/lembretes_enviados.json.

E-mail via as mesmas variáveis do monitor:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM, EMAIL_TO

Uso:
  python lembrete_resultados.py                         # envia
  python lembrete_resultados.py --dry-run               # salva alerts/lembrete_preview.html
  python lembrete_resultados.py --dry-run --hoje 2026-10-29
"""

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from alerta_acoes import DASHBOARD_URL, send_email

BASE = Path(__file__).parent / "alerts"
CAL_FILE = BASE / "calendario.json"
SENT_FILE = BASE / "lembretes_enviados.json"
MARCOS = (14, 7)
BRT = timezone(timedelta(hours=-3))
DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def label(e):
    t = e.get("ticker") or ""
    return t if len(t) <= 6 else e["empresa"]


def marco(dias):
    """Marco do aviso: 7 se faltam até 7 dias, 14 se faltam de 8 a 14."""
    if dias < 0:
        return None
    if dias <= 7:
        return 7
    if dias <= 14:
        return 14
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--hoje", help="AAAA-MM-DD (para testes)")
    args = ap.parse_args()
    hoje = date.fromisoformat(args.hoje) if args.hoje else datetime.now(BRT).date()

    events = json.loads(CAL_FILE.read_text()).get("events", [])
    sent = json.loads(SENT_FILE.read_text()) if SENT_FILE.exists() else {}
    res = [e for e in events if e.get("tipo") == "resultado" and e.get("data") and e.get("status") != "realizado"]
    calls = {(e["empresa"], e["data"]): e for e in events if e.get("tipo") == "teleconferencia" and e.get("data")}

    novos, proximos = [], []
    for e in res:
        d = date.fromisoformat(e["data"])
        dias = (d - hoje).days
        m = marco(dias)
        if m is None:
            continue
        # call no mesmo dia ou até 2 dias depois
        call = next((calls[(e["empresa"], (d + timedelta(k)).isoformat())] for k in range(3)
                     if (e["empresa"], (d + timedelta(k)).isoformat()) in calls), None)
        item = dict(e, dias=dias, marco=m, call=call)
        proximos.append(item)
        key = f"{e['empresa']}|{e['data']}|{m}"
        if key not in sent:
            novos.append((key, item))
    proximos.sort(key=lambda x: (x["data"], label(x)))
    novos.sort(key=lambda x: (x[1]["data"], label(x[1])))

    if not novos:
        print(f"[INFO] {hoje}: nenhum resultado a 14 ou 7 dias ainda não avisado ({len(proximos)} nos próximos 14 dias).")
        return

    from email_layout import DOWN, MUTED, ACCENT, data_table, esc, page, row, section_title, button

    def quando(x):
        d = date.fromisoformat(x["data"])
        s = f"{d:%d/%m} ({DIAS[d.weekday()]})" + (f" · {x['hora']}" if x.get("hora") else "")
        return s

    def falta(x):
        return "hoje" if x["dias"] == 0 else ("amanhã" if x["dias"] == 1 else f"{x['dias']}\u00a0dias")

    def status(x):
        st = x.get("status") or ""
        cor = DOWN if st == "estimado" else "#0a7d32"
        return f'<span style="color:{cor};font-weight:700">{esc(st)}</span>'

    def linha(x):
        call = x["call"]
        call_txt = (f"{date.fromisoformat(call['data']):%d/%m}" + (f" {call['hora']}" if call.get("hora") else "")) if call else "—"
        return [f"<b>{esc(label(x))}</b><br><span style=\"color:{MUTED};font-size:12px\">{esc(x['empresa'])}"
                f"{' · bond' if x.get('grupo') == 'Bonds' else ''}</span>",
                esc(x["evento"]), esc(quando(x)), f"<b>{esc(falta(x))}</b>", esc(call_txt), status(x)]

    hdr = ["Empresa", "Evento", "Data", "Falta", "Call", "Status"]
    al = ["left", "left", "left", "right", "left", "left"]
    body = ""
    for m in (7, 14):
        grupo = [x for _, x in novos if x["marco"] == m]
        if grupo:
            body += section_title(f"Faltam {m} dias ou menos" if m == 7 else "Faltam de 8 a 14 dias")
            body += data_table(hdr, [linha(x) for x in grupo], al)
    resto = [x for x in proximos if f"{x['empresa']}|{x['data']}|{x['marco']}" not in dict(novos)]
    if resto:
        body += section_title("Também nos próximos 14 dias")
        body += data_table(hdr, [linha(x) for x in resto], al)
    if any(x.get("status") == "estimado" for _, x in novos):
        body += row(f'<span style="color:{MUTED}">Datas "estimado" seguem o mesmo trimestre do ano anterior; '
                    "o calendário é revisado todo dia às 19h45 e o aviso sai de novo se a data mudar.</span>")
    for _, x in novos:
        if x.get("obs"):
            body += row(f'<span style="color:{MUTED}"><b>{esc(label(x))}:</b> {esc(x["obs"])}</span>')
    body += button(DASHBOARD_URL, "Abrir o calendário no painel")

    nomes = ", ".join(f"{label(x)} ({falta(x)})" for _, x in novos)
    subject = f"Resultados chegando: {nomes}"
    html_body = page("CALENDÁRIO DE RI · LEMBRETE", "Divulgação de resultados chegando",
                     f"Avisos de 14 e 7 dias · {hoje:%d/%m/%Y}", body,
                     "Fonte: calendário de RI do painel (sites de RI, comunicados ao mercado e press releases).")
    text = "\n".join([subject, ""] + [f"- {label(x)} · {x['evento']} · {quando(x)} · faltam {falta(x)} · {x.get('status')}"
                                      for _, x in novos] + ["", f"Painel: {DASHBOARD_URL}"])
    print(subject)
    print(text)
    if args.dry_run:
        (BASE / "lembrete_preview.html").write_text(html_body)
        print("[INFO] Prévia salva em alerts/lembrete_preview.html.")
        return
    send_email(subject, text, html_body)
    now = datetime.now(BRT).isoformat(timespec="minutes")
    for k, _ in novos:
        sent[k] = now
    limite = (hoje - timedelta(days=60)).isoformat()
    sent = {k: v for k, v in sent.items() if k.split("|")[1] >= limite}
    SENT_FILE.write_text(json.dumps(sent, ensure_ascii=False, indent=1, sort_keys=True))
    print(f"[INFO] E-mail enviado ({len(novos)} aviso(s)).")


if __name__ == "__main__":
    main()
