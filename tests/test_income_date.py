"""Test reguly daty uzyskania przychodu (art. 14 ust. 1c) — single source of truth."""

from dataclasses import dataclass
from datetime import date

from jdg_ksiegowy.tax.income import income_date


@dataclass
class _Inv:
    sale_date: date
    issue_date: date


def test_income_date_is_service_date_when_invoice_issued_later():
    """Typowy B2B: usluga wykonana 31.05, faktura wystawiona 1.06 -> przychod 31.05."""
    inv = _Inv(sale_date=date(2026, 5, 31), issue_date=date(2026, 6, 1))
    assert income_date(inv) == date(2026, 5, 31)


def test_income_date_is_issue_date_for_advance_invoice():
    """Faktura zaliczkowa: wystawiona 1.06 przed wykonaniem 10.06 -> przychod 1.06."""
    inv = _Inv(sale_date=date(2026, 6, 10), issue_date=date(2026, 6, 1))
    assert income_date(inv) == date(2026, 6, 1)


def test_income_date_equal_dates():
    inv = _Inv(sale_date=date(2026, 6, 5), issue_date=date(2026, 6, 5))
    assert income_date(inv) == date(2026, 6, 5)
