"""Kalkulacje podatkowe: netto -> VAT -> brutto -> ryczalt.

ZUS obliczenia w tax/zus.py (single source of truth).
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from jdg_ksiegowy.invoice.models import InvoiceCalc


def calculate_invoice(
    netto: Decimal,
    vat_rate: Decimal = Decimal("23"),
    ryczalt_rate: Decimal = Decimal("12"),
) -> InvoiceCalc:
    """Oblicz wszystkie kwoty z faktury."""
    netto = Decimal(str(netto))
    vat_amount = (netto * vat_rate / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    brutto = netto + vat_amount
    ryczalt_amount = (netto * ryczalt_rate / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return InvoiceCalc(
        netto=netto,
        vat_rate=vat_rate,
        vat_amount=vat_amount,
        brutto=brutto,
        ryczalt_rate=ryczalt_rate,
        ryczalt_amount=ryczalt_amount,
    )


def get_tax_deadlines(invoice_month: int, invoice_year: int) -> dict[str, date]:
    """Zwroc terminy podatkowe za dany miesiac fakturowania."""
    next_month = invoice_month + 1 if invoice_month < 12 else 1
    next_year = invoice_year if invoice_month < 12 else invoice_year + 1

    return {
        "ryczalt": date(next_year, next_month, 20),
        "zus_health": date(next_year, next_month, 20),
        "vat_jpk": date(next_year, next_month, 25),
    }
