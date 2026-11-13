"""Cykliczne kontrakty — auto-fakturowanie wg harmonogramu.

Logika: kontrakt `monthly` z `day_of_month=-1` wystawia fakturę
ostatniego dnia roboczego miesiąca (pn-pt). Inne wartości day_of_month
wystawiają fakturę na konkretny dzień miesiąca.

Runner wywołuje się z cron/schedulera raz dziennie.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from jdg_ksiegowy.invoice.models import Contract, Invoice, InvoiceStatus, LineItem
from jdg_ksiegowy.registry.repository import ContractRepository, InvoiceRepository


@dataclass
class RunResult:
    generated: list[str] = field(default_factory=list)  # numery faktur
    skipped: list[str] = field(default_factory=list)  # kontrakty pominięte


def last_working_day(year: int, month: int) -> date:
    """Zwróć ostatni dzień roboczy (pn-pt) danego miesiąca."""
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    while last.weekday() >= 5:  # 5=sob, 6=nie
        last -= timedelta(days=1)
    return last


def _invoice_due_date(issue_date: date, days: int = 14) -> date:
    return issue_date + timedelta(days=days)


def _contract_issue_date(contract: Contract, year: int, month: int) -> date | None:
    """Zwróć datę wystawienia faktury dla kontraktu w danym miesiącu.

    Zwraca None jeśli kontrakt nie jest wymagalny w tym dniu.
    """
    if contract.cycle != "monthly":
        return None  # quarterly nie jest jeszcze obsługiwane
    day = contract.day_of_month
    if day == -1:
        return last_working_day(year, month)
    try:
        return date(year, month, day)
    except ValueError:
        return last_working_day(year, month)  # np. 31 w miesiącu 30-dniowym


def _invoice_number(contract: Contract, month: int, year: int) -> str:
    """Numer faktury cyklicznej: K{prefix_id}/{MM}/{RRRR}."""
    return f"K{contract.id[:8]}/{month:02d}/{year}"


def _build_invoice(contract: Contract, issue_date: date, number: str) -> Invoice:
    item = LineItem(
        description=contract.description,
        quantity=Decimal("1"),
        unit="usl.",
        unit_price_net=contract.net_amount,
        vat_rate=contract.vat_rate,
    )
    return Invoice(
        id=str(uuid.uuid4()),
        number=number,
        issue_date=issue_date,
        sale_date=issue_date,
        payment_due=_invoice_due_date(issue_date),
        buyer=contract.buyer,
        items=[item],
        status=InvoiceStatus.GENERATED,
    )


def run_contracts(today: date | None = None) -> RunResult:
    """Wygeneruj faktury cykliczne dla kontraktów wymagalnych na dany dzień.

    Idempotentne — wywołanie wielokrotne tego samego dnia nie duplikuje faktur.
    """
    today = today or date.today()
    invoices = InvoiceRepository()
    result = RunResult()

    for contract in ContractRepository().active():
        issue_date = _contract_issue_date(contract, today.year, today.month)
        if issue_date is None or issue_date != today:
            result.skipped.append(contract.id)
            continue

        number = _invoice_number(contract, today.month, today.year)
        if invoices.get(number) is not None:  # idempotencja: numer kodu kontraktu i miesiaca
            result.skipped.append(contract.id)
            continue

        invoices.save(_build_invoice(contract, issue_date, number))
        result.generated.append(number)

    return result
