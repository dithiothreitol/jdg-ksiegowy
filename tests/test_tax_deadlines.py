"""Przypadki brzegowe przesuwania terminow z dni wolnych na dni robocze (PR #8).

Uzupelniaja `test_tax_rules.py`: pelny kalendarz swiat 2026, granica Wigilii, ruchome
swieta i sobota.
"""

from datetime import date, timedelta

import pytest

from jdg_ksiegowy.tax.deadlines import is_business_day, monthly_deadlines, next_business_day

# Dni ustawowo wolne od pracy w 2026 r. (ustawa z 18 stycznia 1951 r.; Wigilia od 2025 r.)
PUBLIC_HOLIDAYS_2026 = [
    date(2026, 1, 1),
    date(2026, 1, 6),
    date(2026, 4, 5),  # Wielkanoc
    date(2026, 4, 6),  # Poniedzialek Wielkanocny
    date(2026, 5, 1),
    date(2026, 5, 3),
    date(2026, 5, 24),  # Zeslanie Ducha Swietego
    date(2026, 6, 4),  # Boze Cialo
    date(2026, 8, 15),
    date(2026, 11, 1),
    date(2026, 11, 11),
    date(2026, 12, 24),
    date(2026, 12, 25),
    date(2026, 12, 26),
]


@pytest.mark.parametrize("day", PUBLIC_HOLIDAYS_2026)
def test_public_holidays_2026_are_days_off(day):
    assert not is_business_day(day)


def test_new_years_eve_is_a_business_day():
    assert is_business_day(date(2026, 12, 31))


def test_christmas_eve_is_a_holiday_only_since_2025():
    assert is_business_day(date(2024, 12, 24))  # wtorek
    assert not is_business_day(date(2025, 12, 24))  # sroda


@pytest.mark.parametrize(
    "easter_sunday",
    [date(2024, 3, 31), date(2025, 4, 20), date(2026, 4, 5), date(2027, 3, 28)],
)
def test_easter_monday_moves_deadline_to_tuesday(easter_sunday):
    easter_monday = easter_sunday + timedelta(days=1)
    assert next_business_day(easter_monday) == easter_monday + timedelta(days=1)


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 6, 20), date(2026, 6, 22)),  # sobota
        (date(2026, 6, 4), date(2026, 6, 5)),  # Boze Cialo
    ],
)
def test_next_business_day(day, expected):
    assert next_business_day(day) == expected


def test_zus_deadline_moves_off_saturday():
    assert monthly_deadlines(5, 2026)["zus"] == date(2026, 6, 22)
