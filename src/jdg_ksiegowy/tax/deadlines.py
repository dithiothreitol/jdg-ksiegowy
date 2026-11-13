"""Terminy podatkowe i skladkowe z przesunieciem na dzien roboczy.

Ordynacja podatkowa art. 12 § 5: gdy ostatni dzien terminu przypada w sobote lub dzien
ustawowo wolny od pracy, termin uplywa nastepnego dnia roboczego. Te sama zasade stosuje
ZUS. Ryczalt za grudzien jest platny do 20 stycznia (od rozliczenia za 2023 r.),
zeznanie PIT-28 do 30 kwietnia, JPK_EWP razem z zeznaniem.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import cache

import holidays


@cache
def _pl_holidays(year: int) -> holidays.HolidayBase:
    return holidays.country_holidays("PL", years=year)


def is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in _pl_holidays(d.year)


def next_business_day(d: date) -> date:
    """Ten sam dzien albo najblizszy kolejny dzien roboczy."""
    while not is_business_day(d):
        d += timedelta(days=1)
    return d


def monthly_deadlines(month: int, year: int) -> dict[str, date]:
    """Terminy za miesiac rozliczeniowy: ryczalt i ZUS do 20., VAT i JPK_V7M do 25."""
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    return {
        "ryczalt": next_business_day(date(next_year, next_month, 20)),
        "zus": next_business_day(date(next_year, next_month, 20)),
        "vat_jpk": next_business_day(date(next_year, next_month, 25)),
    }


def annual_deadlines(year: int) -> dict[str, date]:
    """Zeznanie PIT-28 i ewidencja JPK_EWP za rok podatkowy."""
    pit28 = next_business_day(date(year + 1, 4, 30))
    return {"pit28": pit28, "jpk_ewp": pit28}
