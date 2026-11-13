"""Rozliczenie VAT okresu z przeniesiona nadwyzka (P_39) — z rejestru i zlozonych deklaracji.

Nadwyzka z poprzedniego miesiaca pochodzi z ostatniej przyjetej przez MF deklaracji za ten
okres (pole P_62 z pliku), a gdy jej nie ma — z rozliczenia policzonego z rejestru.
Lancuch zaczyna sie od pierwszego miesiaca z danymi w rejestrze (wczesniej nadwyzka = 0).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from lxml import etree

from jdg_ksiegowy.expenses.models import Expense
from jdg_ksiegowy.invoice.models import Invoice
from jdg_ksiegowy.registry.repository import ExpenseRepository, FilingRepository, InvoiceRepository
from jdg_ksiegowy.tax.jpk import VatSettlement, period_fields, settle_vat

ZERO = Decimal("0")
Period = tuple[int, int]


def previous(period: Period) -> Period:
    year, month = period
    return (year - 1, 12) if month == 1 else (year, month - 1)


@dataclass
class VatLedger:
    """Dane rejestru potrzebne do rozliczen VAT kolejnych miesiecy."""

    invoices: list[Invoice]
    expenses: list[Expense]
    declared: dict[Period, Decimal]  # P_62 z przyjetych deklaracji

    @classmethod
    def load(cls) -> VatLedger:
        declared: dict[Period, Decimal] = {}
        # Lista od najnowszych — pierwsza przyjeta deklaracja okresu jest obowiazujaca.
        for f in FilingRepository().list(form="JPK_V7M"):
            period = (f.year, f.month or 0)
            if f.status == "accepted" and period not in declared and Path(f.file_path).exists():
                declared[period] = _declared_surplus(Path(f.file_path))
        return cls(InvoiceRepository().list(), ExpenseRepository().list(), declared)

    def _invoices(self, period: Period) -> list[Invoice]:
        return [i for i in self.invoices if (i.sale_date.year, i.sale_date.month) == period]

    def _expenses(self, period: Period) -> list[Expense]:
        return [e for e in self.expenses if (e.receive_date.year, e.receive_date.month) == period]

    def _first_period(self) -> Period | None:
        periods = [(i.sale_date.year, i.sale_date.month) for i in self.invoices]
        periods += [(e.receive_date.year, e.receive_date.month) for e in self.expenses]
        periods += list(self.declared)
        return min(periods) if periods else None

    def carry_forward(self, period: Period) -> Decimal:
        """Nadwyzka podatku naliczonego z poprzedniego okresu (P_39)."""
        first = self._first_period()
        prev = previous(period)
        if first is None or prev < first:
            return ZERO
        if prev in self.declared:
            return self.declared[prev]
        return self.settlement(prev).nadwyzka

    def settlement(self, period: Period) -> VatSettlement:
        expenses = self._expenses(period)
        fields = period_fields(self._invoices(period), expenses)
        return settle_vat(fields, expenses, self.carry_forward(period))


def _declared_surplus(path: Path) -> Decimal:
    root = etree.parse(str(path)).getroot()
    return Decimal(root.findtext(".//{*}PozycjeSzczegolowe/{*}P_62") or "0")
