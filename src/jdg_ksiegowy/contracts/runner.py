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

from jdg_ksiegowy.config import settings
from jdg_ksiegowy.invoice.models import Buyer, Invoice, LineItem
from jdg_ksiegowy.registry.db import (
    ContractRecord,
    InvoiceRecord,
    get_active_contracts,
    get_invoices,
    init_db,
    save_invoice,
)


@dataclass
class RunResult:
    generated: list[str] = field(default_factory=list)   # numery faktur
    skipped: list[str] = field(default_factory=list)      # kontrakty pominięte
    errors: list[str] = field(default_factory=list)


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


def _already_issued(contract_id: str, year: int, month: int) -> bool:
    """Sprawdź czy faktura z kontraktu już istnieje w tym miesiącu."""
    all_invoices = get_invoices(month=month, year=year)
    prefix = f"K{contract_id[:8]}"
    return any(inv.number.startswith(prefix) for inv in all_invoices)


def _contract_issue_date(contract: ContractRecord, year: int, month: int) -> date | None:
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


def _invoice_number(contract: ContractRecord, month: int, year: int) -> str:
    """Numer faktury cyklicznej: K{prefix_id}/{MM}/{RRRR}."""
    return f"K{contract.id[:8]}/{month:02d}/{year}"


def _build_invoice(contract: ContractRecord, issue_date: date, number: str) -> Invoice:
    buyer = Buyer(
        name=contract.buyer_name,
        nip=contract.buyer_nip,
        address=contract.buyer_address or "",
        email=contract.buyer_email,
    )
    vat_rate = Decimal(str(contract.vat_rate)) if contract.vat_rate is not None else Decimal("23")
    item = LineItem(
        description=contract.description,
        quantity=Decimal("1"),
        unit="usl.",
        unit_price_net=Decimal(str(contract.net_amount)),
        vat_rate=vat_rate,
    )
    return Invoice(
        id=str(uuid.uuid4()),
        number=number,
        issue_date=issue_date,
        sale_date=issue_date,
        payment_due=_invoice_due_date(issue_date),
        buyer=buyer,
        items=[item],
    )


def _to_record(inv: Invoice) -> InvoiceRecord:
    return InvoiceRecord(
        id=inv.id,
        number=inv.number,
        issue_date=inv.issue_date,
        sale_date=inv.sale_date,
        payment_due=inv.payment_due,
        buyer_name=inv.buyer.name,
        buyer_nip=inv.buyer.nip,
        buyer_address=inv.buyer.address,
        total_net=inv.total_net,
        total_vat=inv.total_vat,
        total_gross=inv.total_gross,
        vat_rate=inv.items[0].vat_rate if inv.items else Decimal(str(settings.seller.vat_rate)),
        status="generated",
    )


def run_contracts(today: date | None = None) -> RunResult:
    """Wygeneruj faktury cykliczne dla kontraktów wymagalnych na dany dzień.

    Idempotentne — wywołanie wielokrotne tego samego dnia nie duplikuje faktur.
    """
    today = today or date.today()
    init_db()
    contracts = get_active_contracts()
    result = RunResult()

    for contract in contracts:
        issue_date = _contract_issue_date(contract, today.year, today.month)
        if issue_date is None or issue_date != today:
            result.skipped.append(contract.id)
            continue

        if _already_issued(contract.id, today.year, today.month):
            result.skipped.append(contract.id)
            continue

        number = _invoice_number(contract, today.month, today.year)
        try:
            inv = _build_invoice(contract, issue_date, number)
            record = _to_record(inv)
            save_invoice(record)
            result.generated.append(number)
        except Exception as exc:
            result.errors.append(f"{contract.id}: {exc}")

    return result
