"""Kontrakty cykliczne — kiedy i jaka fakture wystawic (czysta logika, bez zapisu).

Kontrakt `monthly` z `day_of_month=-1` fakturuje ostatniego dnia roboczego miesiaca
(z uwzglednieniem swiat), z innym `day_of_month` — tego dnia (albo w ostatni dzien
roboczy, gdy miesiac jest krotszy). Zapis i dokumenty robi wspolny potok wystawiania.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from jdg_ksiegowy.invoice.models import Contract, Invoice, InvoiceStatus, LineItem
from jdg_ksiegowy.tax.deadlines import is_business_day

PAYMENT_DAYS = 14


def last_working_day(year: int, month: int) -> date:
    last = (date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)) - timedelta(days=1)
    while not is_business_day(last):
        last -= timedelta(days=1)
    return last


def issue_date_for(contract: Contract, year: int, month: int) -> date | None:
    """Dzien wystawienia faktury z kontraktu w danym miesiacu (None — kontrakt nie miesieczny)."""
    if contract.cycle != "monthly":
        return None
    if contract.day_of_month == -1:
        return last_working_day(year, month)
    try:
        return date(year, month, contract.day_of_month)
    except ValueError:
        return last_working_day(year, month)


def invoice_number_for(contract: Contract, month: int, year: int) -> str:
    """Numer faktury cyklicznej: K{8 znakow id}/MM/RRRR — klucz idempotencji."""
    return f"K{contract.id[:8]}/{month:02d}/{year}"


def build_invoice(contract: Contract, issue_date: date) -> Invoice:
    return Invoice(
        id=str(uuid.uuid4()),
        number=invoice_number_for(contract, issue_date.month, issue_date.year),
        issue_date=issue_date,
        sale_date=issue_date,
        payment_due=issue_date + timedelta(days=PAYMENT_DAYS),
        buyer=contract.buyer,
        items=[
            LineItem(
                description=contract.description,
                quantity=Decimal("1"),
                unit="usl.",
                unit_price_net=contract.net_amount,
                vat_rate=contract.vat_rate,
            )
        ],
        status=InvoiceStatus.GENERATED,
    )
