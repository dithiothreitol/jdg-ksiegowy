"""Uzupelnienie numerow KSeF dla faktur wyslanych przed poprawka klienta.

Do wersji 0.2 rejestr zapisywal numer referencyjny wysylki zamiast numeru KSeF,
wiec JPK oznaczal takie faktury jako BFK. Odpytujemy KSeF o faktury, w ktorych
jestesmy sprzedawca, i dopasowujemy je po numerze faktury (P_2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from jdg_ksiegowy.ksef.client import KSeFClient
from jdg_ksiegowy.registry.repository import InvoiceRepository


@dataclass(frozen=True)
class BackfillMatch:
    invoice_number: str
    ksef_number: str
    acquired_at: datetime | None


@dataclass(frozen=True)
class BackfillResult:
    matched: list[BackfillMatch]
    missing: list[str]  # faktury bez numeru KSeF, ktorych KSeF nie zna
    applied: bool


def backfill_ksef_numbers(
    client: KSeFClient,
    repo: InvoiceRepository,
    *,
    today: date,
    apply: bool,
) -> BackfillResult:
    """Znajdz numery KSeF faktur, ktore ich nie maja; zapisz gdy `apply`."""
    pending = [i for i in repo.list() if not i.ksef_number and i.issue_date.year >= 2026]
    if not pending:
        return BackfillResult(matched=[], missing=[], applied=apply)

    date_from = min(i.issue_date for i in pending)
    metadata = client.query_metadata(date_from, today, role="seller", include_corrections=True)
    by_number = {m.invoice_number: m for m in metadata}

    matched: list[BackfillMatch] = []
    missing: list[str] = []
    for inv in pending:
        meta = by_number.get(inv.number)
        if meta is None:
            missing.append(inv.number)
            continue
        matched.append(BackfillMatch(inv.number, meta.ksef_number, meta.acquisition_date))

    if apply:
        for m in matched:
            repo.set_ksef_number(m.invoice_number, m.ksef_number, m.acquired_at)
    return BackfillResult(matched=matched, missing=missing, applied=apply)
