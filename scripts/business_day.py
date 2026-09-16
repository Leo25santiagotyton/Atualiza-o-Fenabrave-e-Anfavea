#!/usr/bin/env python3
"""Determina se hoje é o primeiro dia útil da semana ou do mês, considerando
o calendário de feriados nacionais do Brasil, e calcula os dois períodos a
comparar nos relatórios do pipeline (o período que acabou de fechar vs. o
anterior a ele).

Uso:
  python3 business_day.py weekly    # semana passada vs. retrasada
  python3 business_day.py monthly   # mês passado vs. anterior

Saída:
  "SKIP"                 -> hoje não é o primeiro dia útil do período; nada a fazer
  "RUN <json>"           -> hoje é o dia certo; json traz as datas dos períodos
"""
import json
import sys
from datetime import date, timedelta


def easter(year: int) -> date:
    """Data da Páscoa (algoritmo de Gauss/Meeus, calendário gregoriano)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def national_holidays(year: int) -> set:
    p = easter(year)
    fixed = {
        date(year, 1, 1),    # Confraternização Universal
        date(year, 4, 21),   # Tiradentes
        date(year, 5, 1),    # Dia do Trabalho
        date(year, 9, 7),    # Independência
        date(year, 10, 12),  # Nossa Senhora Aparecida
        date(year, 11, 2),   # Finados
        date(year, 11, 15),  # Proclamação da República
        date(year, 11, 20),  # Consciência Negra
        date(year, 12, 25),  # Natal
    }
    movable = {
        p - timedelta(days=48),  # Carnaval (segunda)
        p - timedelta(days=47),  # Carnaval (terça)
        p - timedelta(days=2),   # Sexta-feira Santa
        p + timedelta(days=60),  # Corpus Christi
    }
    return fixed | movable


def is_business_day(d: date) -> bool:
    if d.weekday() >= 5:  # 5=sábado, 6=domingo
        return False
    return d not in national_holidays(d.year)


def week_bounds(d: date):
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=7)  # fim exclusivo


def month_bounds(d: date):
    start = d.replace(day=1)
    nxt = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
    return start, nxt  # fim exclusivo


def _prev_month_start(d: date) -> date:
    return date(d.year - 1, 12, 1) if d.month == 1 else date(d.year, d.month - 1, 1)


def is_first_business_day_of_week(today: date) -> bool:
    monday, _ = week_bounds(today)
    if not is_business_day(today):
        return False
    d = monday
    while d < today:
        if is_business_day(d):
            return False
        d += timedelta(days=1)
    return True


def is_first_business_day_of_month(today: date) -> bool:
    start, _ = month_bounds(today)
    if not is_business_day(today):
        return False
    d = start
    while d < today:
        if is_business_day(d):
            return False
        d += timedelta(days=1)
    return True


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("weekly", "monthly"):
        print("uso: business_day.py weekly|monthly", file=sys.stderr)
        sys.exit(2)

    today = date.today()
    mode = sys.argv[1]

    if mode == "weekly":
        if not is_first_business_day_of_week(today):
            print("SKIP")
            return
        this_monday, _ = week_bounds(today)
        cur_start, cur_end = this_monday - timedelta(days=7), this_monday
        prev_start, prev_end = cur_start - timedelta(days=7), cur_start
        label = "semana"
    else:
        if not is_first_business_day_of_month(today):
            print("SKIP")
            return
        this_start, _ = month_bounds(today)
        cur_start, cur_end = _prev_month_start(this_start), this_start
        prev_start, prev_end = _prev_month_start(cur_start), cur_start
        label = "mes"

    out = {
        "label": label,
        "today": today.isoformat(),
        "current": {"start": cur_start.isoformat(), "end": cur_end.isoformat()},
        "previous": {"start": prev_start.isoformat(), "end": prev_end.isoformat()},
    }
    print("RUN " + json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
