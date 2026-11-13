"""Platnosci faktur — import wyciagu CSV z banku i dopasowanie przelewow."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from jdg_ksiegowy.invoice.models import Invoice


@dataclass
class BankRow:
    """Wiersz z wyciagu bankowego (CSV)."""

    transaction_date: date
    amount: Decimal
    description: str
    raw: str = ""


@dataclass
class MatchResult:
    matched: list[tuple[BankRow, Invoice]] = field(default_factory=list)
    unmatched_bank: list[BankRow] = field(default_factory=list)
    unmatched_invoices: list[Invoice] = field(default_factory=list)


def awaiting_payment(invoice: Invoice) -> bool:
    """Naleznosc do zaplaty: niezaplacona i na plus (korekta zmniejszajaca nie jest naleznoscia)."""
    return invoice.paid_at is None and invoice.total_gross > 0


def overdue(invoices: list[Invoice], today: date) -> list[Invoice]:
    """Naleznosci po terminie."""
    return [i for i in invoices if awaiting_payment(i) and i.payment_due < today]


def unpaid(invoices: list[Invoice], today: date) -> list[Invoice]:
    """Naleznosci przed terminem."""
    return [i for i in invoices if awaiting_payment(i) and i.payment_due >= today]


def _amount(raw: str) -> Decimal:
    return Decimal(raw.strip().replace(" ", "").replace("\xa0", "").replace(",", "."))


def _parse_mbank_csv(content: str) -> list[BankRow]:
    """CSV mBanku: #Data operacji;Opis operacji;...;Kwota;Waluta."""
    rows = []
    for row in csv.DictReader(io.StringIO(content), delimiter=";"):
        raw_date = (row.get("#Data operacji") or "").strip()
        if not raw_date:
            continue
        try:
            rows.append(
                BankRow(
                    date.fromisoformat(raw_date),
                    _amount(row.get("Kwota") or "0"),
                    (row.get("Opis operacji") or "").strip(),
                    str(row),
                )
            )
        except (ValueError, InvalidOperation):
            continue  # stopki/podsumowania wyciagu nie sa transakcjami
    return rows


def _parse_generic_csv(content: str) -> list[BankRow]:
    """CSV z naglowkiem: kolumny daty, kwoty i opisu rozpoznawane po nazwie."""
    reader = csv.DictReader(io.StringIO(content))
    fields = reader.fieldnames or []
    date_col = next((f for f in fields if "date" in f.lower() or "data" in f.lower()), None)
    amount_col = next((f for f in fields if "amount" in f.lower() or "kwota" in f.lower()), None)
    desc_col = next((f for f in fields if "desc" in f.lower() or "opis" in f.lower()), None)
    if not date_col or not amount_col:
        return []
    rows = []
    for row in reader:
        try:
            rows.append(
                BankRow(
                    date.fromisoformat(row[date_col].strip()),
                    _amount(row[amount_col]),
                    row[desc_col].strip() if desc_col else "",
                    str(row),
                )
            )
        except (ValueError, InvalidOperation):
            continue
    return rows


def parse_bank_csv(path: Path | str) -> list[BankRow]:
    """Rozpoznaj format CSV z banku i zwroc transakcje."""
    content = Path(path).read_text(encoding="utf-8-sig")
    if "#Data operacji" in content[:500]:
        return _parse_mbank_csv(content)
    return _parse_generic_csv(content)


def _invoice_number_in_text(text: str) -> str | None:
    """Numer faktury z tytulu przelewu (np. A1/04/2026, K12345678/04/2026)."""
    m = re.search(r"[AK]\w{1,8}/\d{2}/\d{4}", text)
    return m.group(0) if m else None


def match_payments(bank_rows: list[BankRow], invoices: list[Invoice]) -> MatchResult:
    """Dopasuj wplywy do niezaplaconych faktur.

    1. numer faktury w tytule przelewu (najsilniejszy sygnal),
    2. kwota brutto + data w oknie +-30 dni od terminu platnosci.
    """
    result = MatchResult()
    pending = {inv.number: inv for inv in invoices if awaiting_payment(inv)}
    used_invoices: set[str] = set()
    used_rows: set[int] = set()

    for i, row in enumerate(bank_rows):
        if row.amount <= 0:
            continue
        nr = _invoice_number_in_text(row.description)
        if nr and nr in pending and nr not in used_invoices:
            result.matched.append((row, pending[nr]))
            used_invoices.add(nr)
            used_rows.add(i)

    for i, row in enumerate(bank_rows):
        if i in used_rows or row.amount <= 0:
            continue
        for nr, inv in pending.items():
            if nr in used_invoices:
                continue
            if (
                inv.total_gross == row.amount
                and abs((row.transaction_date - inv.payment_due).days) <= 30
            ):
                result.matched.append((row, inv))
                used_invoices.add(nr)
                used_rows.add(i)
                break

    result.unmatched_bank = [
        r for i, r in enumerate(bank_rows) if i not in used_rows and r.amount > 0
    ]
    result.unmatched_invoices = [inv for nr, inv in pending.items() if nr not in used_invoices]
    return result
