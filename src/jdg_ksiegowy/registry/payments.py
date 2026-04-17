"""Śledzenie płatności — oznaczanie faktur jako zapłacone, import CSV z banku."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from jdg_ksiegowy.registry.db import InvoiceRecord, get_invoices, get_session, init_db


@dataclass
class MarkPaidResult:
    invoice_number: str
    success: bool
    error: str = ""


@dataclass
class BankRow:
    """Wiersz z wyciągu bankowego (CSV)."""
    transaction_date: date
    amount: Decimal
    description: str
    raw: str = ""


@dataclass
class MatchResult:
    matched: list[tuple[BankRow, InvoiceRecord]] = field(default_factory=list)
    unmatched_bank: list[BankRow] = field(default_factory=list)
    unmatched_invoices: list[InvoiceRecord] = field(default_factory=list)


def mark_paid(invoice_number: str, paid_at: datetime | None = None) -> MarkPaidResult:
    """Oznacz fakturę jako zapłaconą w SQLite."""
    init_db()
    paid_at = paid_at or datetime.now()
    with get_session() as session:
        inv = session.query(InvoiceRecord).filter(
            InvoiceRecord.number == invoice_number
        ).first()
        if inv is None:
            return MarkPaidResult(invoice_number, False, f"Faktura {invoice_number!r} nie istnieje")
        if inv.paid_at is not None:
            return MarkPaidResult(invoice_number, False, f"Faktura {invoice_number!r} jest juz zaplacona ({inv.paid_at})")
        inv.paid_at = paid_at
        inv.status = "paid"
        session.commit()
    return MarkPaidResult(invoice_number, True)


def get_overdue_invoices(today: date | None = None) -> list[InvoiceRecord]:
    """Zwróć faktury po terminie płatności (niezapłacone)."""
    init_db()
    today = today or date.today()
    all_inv = get_invoices()
    return [i for i in all_inv if not i.paid_at and i.payment_due < today]


def get_unpaid_invoices(today: date | None = None) -> list[InvoiceRecord]:
    """Zwróć faktury niezapłacone (przed terminem)."""
    init_db()
    today = today or date.today()
    all_inv = get_invoices()
    return [i for i in all_inv if not i.paid_at and i.payment_due >= today]


def _parse_mbank_csv(content: str) -> list[BankRow]:
    """Parser CSV mBanku (format: #Data operacji;Opis operacji;...;Kwota;Waluta)."""
    rows = []
    reader = csv.DictReader(io.StringIO(content), delimiter=";")
    for row in reader:
        try:
            raw_date = row.get("#Data operacji", "").strip()
            raw_amount = row.get("Kwota", "0").strip().replace(" ", "").replace(",", ".")
            description = row.get("Opis operacji", "").strip()
            if not raw_date:
                continue
            txn_date = date.fromisoformat(raw_date)
            amount = Decimal(raw_amount)
            rows.append(BankRow(txn_date, amount, description, str(row)))
        except Exception:
            continue
    return rows


def _parse_generic_csv(content: str) -> list[BankRow]:
    """Parser generyczny CSV: date,amount,description (pierwsza linia = nagłówek)."""
    rows = []
    reader = csv.DictReader(io.StringIO(content))
    fields = reader.fieldnames or []
    date_col = next((f for f in fields if "date" in f.lower() or "data" in f.lower()), None)
    amount_col = next((f for f in fields if "amount" in f.lower() or "kwota" in f.lower()), None)
    desc_col = next((f for f in fields if "desc" in f.lower() or "opis" in f.lower()), None)
    if not date_col or not amount_col:
        return rows
    for row in reader:
        try:
            raw_amount = row[amount_col].strip().replace(" ", "").replace(",", ".")
            amount = Decimal(raw_amount)
            txn_date = date.fromisoformat(row[date_col].strip())
            desc = row[desc_col].strip() if desc_col else ""
            rows.append(BankRow(txn_date, amount, desc, str(row)))
        except Exception:
            continue
    return rows


def parse_bank_csv(path: Path | str) -> list[BankRow]:
    """Auto-detect format CSV z banku i zwróć wiersze transakcji."""
    content = Path(path).read_text(encoding="utf-8-sig")
    if "#Data operacji" in content[:500]:
        return _parse_mbank_csv(content)
    return _parse_generic_csv(content)


def _invoice_number_in_text(text: str) -> str | None:
    """Wyciągnij numer faktury z tytułu przelewu (np. A1/04/2026, K12345678/04/2026)."""
    m = re.search(r"[AK]\d{1,8}/\d{2}/\d{4}", text)
    return m.group(0) if m else None


def match_payments(bank_rows: list[BankRow], invoices: list[InvoiceRecord]) -> MatchResult:
    """Dopasuj przelewy bankowe do niezapłaconych faktur.

    Strategia:
    1. Numer faktury w tytule przelewu (najsilniejszy sygnał)
    2. Kwota brutto + data (tolerancja 30 dni od terminu)
    """
    result = MatchResult()
    unpaid = {inv.number: inv for inv in invoices if not inv.paid_at}
    used_invoice_numbers: set[str] = set()
    used_bank_indices: set[int] = set()

    # Przejście 1: numer faktury w tytule
    for i, row in enumerate(bank_rows):
        if row.amount <= 0:  # pominij obciazenia
            continue
        nr = _invoice_number_in_text(row.description)
        if nr and nr in unpaid and nr not in used_invoice_numbers:
            result.matched.append((row, unpaid[nr]))
            used_invoice_numbers.add(nr)
            used_bank_indices.add(i)

    # Przejście 2: kwota + okno czasowe (±30 dni od payment_due)
    for i, row in enumerate(bank_rows):
        if i in used_bank_indices or row.amount <= 0:
            continue
        for nr, inv in unpaid.items():
            if nr in used_invoice_numbers:
                continue
            inv_gross = Decimal(str(inv.total_gross))
            days_diff = abs((row.transaction_date - inv.payment_due).days)
            if inv_gross == row.amount and days_diff <= 30:
                result.matched.append((row, inv))
                used_invoice_numbers.add(nr)
                used_bank_indices.add(i)
                break

    result.unmatched_bank = [r for i, r in enumerate(bank_rows)
                              if i not in used_bank_indices and r.amount > 0]
    result.unmatched_invoices = [inv for nr, inv in unpaid.items()
                                  if nr not in used_invoice_numbers]
    return result
