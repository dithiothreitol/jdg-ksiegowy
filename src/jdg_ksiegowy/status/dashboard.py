"""Stan ksiegowosci na dzien: terminy z kwotami, faktury po terminie, podsumowanie miesiaca.

Czyta rejestr (faktury, koszty, zaplaty, deklaracje) i nie siega do sieci. Kwoty
zobowiazan licza te same funkcje co raporty (`tax.obligations`, `tax.vat_period`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum

from jdg_ksiegowy.config import settings
from jdg_ksiegowy.expenses.models import Expense
from jdg_ksiegowy.invoice.models import Invoice
from jdg_ksiegowy.registry.payments import overdue, unpaid
from jdg_ksiegowy.registry.repository import TaxPayment, TaxPaymentRepository
from jdg_ksiegowy.tax.deadlines import monthly_deadlines
from jdg_ksiegowy.tax.obligations import monthly_contributions, monthly_ryczalt, social_mode_on
from jdg_ksiegowy.tax.vat_period import VatLedger, previous
from jdg_ksiegowy.tax.zus import MissingTaxParamsError

ZERO = Decimal("0")


class ReminderLevel(StrEnum):
    INFO = "info"  # termin za >7 dni
    WARN = "warn"  # termin za 1-7 dni
    URGENT = "urgent"  # dzis lub jutro
    OVERDUE = "overdue"  # po terminie
    PAID = "paid"  # zaplacone (wg ewidencji zaplat)


@dataclass(frozen=True)
class Reminder:
    label: str
    due_date: date
    amount: Decimal | None  # None gdy nie da sie policzyc
    level: ReminderLevel
    days_until: int  # ujemne = po terminie
    key: str = ""  # stabilny identyfikator (synchronizacja z kalendarzem)


@dataclass
class DashboardSnapshot:
    today: date
    reminders: list[Reminder] = field(default_factory=list)
    unpaid_invoices: list[Invoice] = field(default_factory=list)
    overdue_invoices: list[Invoice] = field(default_factory=list)
    month_sales_net: Decimal = ZERO
    month_sales_vat: Decimal = ZERO
    month_expenses_net: Decimal = ZERO
    month_expenses_vat: Decimal = ZERO
    estimated_ryczalt: Decimal = ZERO
    estimated_zus: Decimal | None = ZERO
    notes: list[str] = field(default_factory=list)


class Dashboard:
    def __init__(self, today: date | None = None):
        self.today = today or date.today()

    def snapshot(self) -> DashboardSnapshot:
        ledger = VatLedger.load()
        invoices, expenses = ledger.invoices, ledger.expenses
        payments = TaxPaymentRepository().list()
        year, month = self.today.year, self.today.month
        prev_year, prev_month = previous((year, month))

        snap = DashboardSnapshot(today=self.today)
        snap.unpaid_invoices = unpaid(invoices, self.today)
        snap.overdue_invoices = overdue(invoices, self.today)
        current = [i for i in invoices if (i.sale_date.year, i.sale_date.month) == (year, month)]
        snap.month_sales_net = sum((i.total_net for i in current), ZERO)
        snap.month_sales_vat = sum((i.total_vat for i in current), ZERO)
        snap.month_expenses_net, snap.month_expenses_vat = _deductible(expenses, year, month)

        snap.estimated_ryczalt = monthly_ryczalt(
            invoices, payments, prev_year, prev_month, settings.seller.ryczalt_rate
        ).tax
        try:
            snap.estimated_zus = monthly_contributions(
                invoices,
                payments,
                prev_year,
                prev_month,
                social_mode=social_mode_on(date(prev_year, prev_month, 1)),
                voluntary_sickness=settings.seller.zus_voluntary_sickness,
            ).total
        except MissingTaxParamsError as e:
            snap.estimated_zus = None
            snap.notes.append(str(e))
        vat_to_pay = ledger.settlement((prev_year, prev_month)).to_pay

        snap.reminders = self._tax_reminders(
            prev_year, prev_month, snap.estimated_ryczalt, snap.estimated_zus, vat_to_pay, payments
        )
        snap.reminders += self._invoice_reminders(snap.overdue_invoices, snap.unpaid_invoices)
        snap.reminders.sort(key=lambda r: r.due_date)
        return snap

    def _tax_reminders(
        self,
        year: int,
        month: int,
        ryczalt: Decimal,
        zus: Decimal | None,
        vat: Decimal,
        payments: list[TaxPayment],
    ) -> list[Reminder]:
        deadlines = monthly_deadlines(month, year)
        period = f"{year}-{month:02d}"
        name = f"{month:02d}/{year}"
        paid = {p.type for p in payments if (p.year, p.month) == (year, month) and p.paid_at}
        items = [
            (f"ryczalt-{period}", f"Ryczałt za {name}", deadlines["ryczalt"], ryczalt, "ryczalt"),
            (f"zus-{period}", f"ZUS za {name}", deadlines["zus"], zus, "zus_health"),
            (f"vat_jpk-{period}", f"VAT + JPK_V7M za {name}", deadlines["vat_jpk"], vat, "vat"),
        ]
        return [
            self._reminder(key, label, due, amount, paid=kind in paid)
            for key, label, due, amount, kind in items
        ]

    def _invoice_reminders(self, overdue: list[Invoice], unpaid: list[Invoice]) -> list[Reminder]:
        out = [
            self._reminder(
                f"invoice-{inv.number}",
                f"Faktura {inv.number} ({inv.buyer.name}) — PO TERMINIE",
                inv.payment_due,
                inv.total_gross,
            )
            for inv in overdue
        ]
        out += [
            self._reminder(
                f"invoice-{inv.number}",
                f"Faktura {inv.number} ({inv.buyer.name})",
                inv.payment_due,
                inv.total_gross,
            )
            for inv in unpaid
            if (inv.payment_due - self.today).days <= 7
        ]
        return out

    def _reminder(
        self, key: str, label: str, due: date, amount: Decimal | None, *, paid: bool = False
    ) -> Reminder:
        days = (due - self.today).days
        level = ReminderLevel.PAID if paid else self._level_for(days)
        return Reminder(
            label=label, due_date=due, amount=amount, level=level, days_until=days, key=key
        )

    @staticmethod
    def _level_for(days_until: int) -> ReminderLevel:
        if days_until < 0:
            return ReminderLevel.OVERDUE
        if days_until <= 1:
            return ReminderLevel.URGENT
        if days_until <= 7:
            return ReminderLevel.WARN
        return ReminderLevel.INFO


def _deductible(expenses: list[Expense], year: int, month: int) -> tuple[Decimal, Decimal]:
    rows = [e for e in expenses if (e.receive_date.year, e.receive_date.month) == (year, month)]
    return (
        sum((e.deductible_net for e in rows), ZERO),
        sum((e.deductible_vat for e in rows), ZERO),
    )
