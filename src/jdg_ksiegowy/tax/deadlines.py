"""Przesuwanie terminow podatkowych i skladkowych z dni wolnych na dni robocze.

Art. 12 par. 5 Ordynacji podatkowej: termin przypadajacy w sobote lub dzien ustawowo
wolny od pracy konczy sie w nastepnym dniu po dniu lub dniach wolnych. Do skladek ZUS
przepis stosuje sie odpowiednio (art. 31 ustawy o systemie ubezpieczen spolecznych).
Lista dni wolnych: ustawa z 18 stycznia 1951 r. o dniach wolnych od pracy.
"""

from __future__ import annotations

from datetime import date, timedelta

CHRISTMAS_EVE_HOLIDAY_SINCE = 2025


def easter_sunday(year: int) -> date:
    """Wielkanoc w kalendarzu gregorianskim (algorytm Meeusa/Jonesa/Butchera)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month, day = divmod(h + m - 7 * n + 114, 31)
    return date(year, month, day + 1)


def polish_public_holidays(year: int) -> set[date]:
    """Dni ustawowo wolne od pracy w danym roku."""
    easter = easter_sunday(year)
    holidays = {
        date(year, 1, 1),
        date(year, 1, 6),
        easter,
        easter + timedelta(days=1),
        date(year, 5, 1),
        date(year, 5, 3),
        easter + timedelta(days=49),  # Zeslanie Ducha Swietego
        easter + timedelta(days=60),  # Boze Cialo
        date(year, 8, 15),
        date(year, 11, 1),
        date(year, 11, 11),
        date(year, 12, 25),
        date(year, 12, 26),
    }
    if year >= CHRISTMAS_EVE_HOLIDAY_SINCE:
        holidays.add(date(year, 12, 24))
    return holidays


def next_working_day(day: date) -> date:
    """Zwroc `day`, a gdy to sobota, niedziela lub swieto: najblizszy dzien roboczy."""
    while day.weekday() >= 5 or day in polish_public_holidays(day.year):
        day += timedelta(days=1)
    return day
