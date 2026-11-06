"""Testy przesuwania terminow podatkowych z dni wolnych na dni robocze."""

from datetime import date

import pytest

from jdg_ksiegowy.invoice.calculator import get_tax_deadlines
from jdg_ksiegowy.tax.deadlines import easter_sunday, next_working_day, polish_public_holidays
from jdg_ksiegowy.zus.dra import dra_deadline


@pytest.mark.parametrize(
    ("year", "expected"),
    [
        (2024, date(2024, 3, 31)),
        (2025, date(2025, 4, 20)),
        (2026, date(2026, 4, 5)),
        (2027, date(2027, 3, 28)),
    ],
)
def test_easter_sunday(year, expected):
    assert easter_sunday(year) == expected


def test_2026_has_fourteen_public_holidays():
    assert len(polish_public_holidays(2026)) == 14


def test_christmas_eve_is_a_holiday_only_since_2025():
    assert date(2024, 12, 24) not in polish_public_holidays(2024)
    assert date(2025, 12, 24) in polish_public_holidays(2025)


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 11, 20), date(2026, 11, 20)),  # piatek roboczy
        (date(2026, 6, 20), date(2026, 6, 22)),  # sobota
        (date(2026, 12, 20), date(2026, 12, 21)),  # niedziela
        (date(2026, 12, 25), date(2026, 12, 28)),  # swieta i weekend
        (date(2026, 6, 4), date(2026, 6, 5)),  # Boze Cialo
    ],
)
def test_next_working_day(day, expected):
    assert next_working_day(day) == expected


def test_tax_deadlines_move_off_days_off():
    deadlines = get_tax_deadlines(11, 2026)

    assert deadlines["ryczalt"] == date(2026, 12, 21)
    assert deadlines["zus_health"] == date(2026, 12, 21)
    assert deadlines["vat_jpk"] == date(2026, 12, 28)


def test_dra_deadline_moves_off_days_off():
    assert dra_deadline(5, 2026) == date(2026, 6, 22)
