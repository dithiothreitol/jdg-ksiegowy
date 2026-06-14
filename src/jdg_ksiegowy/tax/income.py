"""Data uzyskania przychodu dla podatku dochodowego (art. 14 ust. 1c ustawy o PIT).

Jedno źródło prawdy dla momentu powstania przychodu ryczałtowego — używane przez PIT-28
(raport roczny) i dashboard (estymata miesięczna). To NIE to samo co moment obowiązku VAT
(art. 19a = data sprzedaży), którego JPK_V7M używa osobno.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol


class HasInvoiceDates(Protocol):
    """Cokolwiek z datą sprzedaży i wystawienia — InvoiceRecord (rejestr) lub Invoice (domena)."""

    sale_date: date
    issue_date: date


def income_date(inv: HasInvoiceDates) -> date:
    """Dzień powstania przychodu wg art. 14 ust. 1c: dzień wykonania usługi (`sale_date`),
    nie później niż dzień wystawienia faktury (`issue_date`) — zwracamy wcześniejszą z dwóch.

    Datę zapłaty pomijamy: w typowym B2B faktura jest wystawiana po wykonaniu usługi i
    opłacana później, więc najwcześniejsza jest `sale_date`; przy fakturze zaliczkowej
    (`issue_date` < `sale_date`) wygrywa `issue_date`.
    """
    return min(inv.sale_date, inv.issue_date)
