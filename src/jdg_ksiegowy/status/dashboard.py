"""Generator snapshotu JDG: nadchodzace/zalegle terminy, stan faktur, podsumowanie miesiaca.

Dashboard dziala odczytujac wylacznie z SQLite + liczac terminy z `tax.zus`
i `invoice.calculator` — nie hitsuje sieci.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from jdg_ksiegowy.config import settings
from jdg_ksiegowy.invoice.calculator import get_tax_deadlines
from jdg_ksiegowy.registry.db import (
    ExpenseRecord,
    InvoiceRecord,
    get_expenses,
    get_invoices,
    init_db,
)
from jdg_ksiegowy.tax.zus import get_zus_tier


class ReminderLevel(StrEnum):
    INFO = "info"  # termin za >7 dni
    WARN = "warn"  # termin za 1-7 dni
    URGENT = "urgent"  # dzis lub jutro
    OVERDUE = "overdue"  # po terminie


@dataclass(frozen=True)
class Reminder:
    """Pojedynczy termin/przypomnienie."""

    label: str  # "Ryczalt za marzec 2026"
    due_date: date
    amount: Decimal | None  # None gdy nieznana
    level: ReminderLevel
    days_until: int  # ujemne = po terminie


@dataclass
class DashboardSnapshot:
    today: date
    reminders: list[Reminder] = field(default_factory=list)
    unpaid_invoices: list[InvoiceRecord] = field(default_factory=list)
    overdue_invoices: list[InvoiceRecord] = field(default_factory=list)
    month_sales_net: Decimal = Decimal("0")
    month_sales_vat: Decimal = Decimal("0")
    month_expenses_net: Decimal = Decimal("0")
    month_expenses_vat: Decimal = Decimal("0")
    estimated_ryczalt: Decimal = Decimal("0")
    estimated_zus: Decimal = Decimal("0")


class Dashboard:
    """Liczy snapshot stanu ksiegowosci na zadany dzien."""

    def __init__(self, today: date | None = None):
        self.today = today or date.today()

    def snapshot(self) -> DashboardSnapshot:
        init_db()
        invoices = get_invoices()
        expenses = get_expenses()

        prev_month = self.today.month - 1 if self.today.month > 1 else 12
        prev_year = self.today.year if self.today.month > 1 else self.today.year - 1

        snap = DashboardSnapshot(today=self.today)
        snap.unpaid_invoices = [i for i in invoices if not i.paid_at and i.payment_due >= self.today]
        snap.overdue_invoices = [i for i in invoices if not i.paid_at and i.payment_due < self.today]
        snap.month_sales_net, snap.month_sales_vat = self._sum_invoices(invoices, self.today.year, self.today.month)
        snap.month_expenses_net, snap.month_expenses_vat = self._sum_expenses(expenses, self.today.year, self.today.month)

        # Ryczalt za poprzedni miesiac (platne do 20-go obecnego)
        prev_sales_net, _ = self._sum_invoices(invoices, prev_year, prev_month)
        snap.estimated_ryczalt = (
            prev_sales_net * settings.seller.ryczalt_rate / 100
        ).quantize(Decimal("0.01"))

        # ZUS zdrowotne — biezacy miesiac (platne do 20-go nastepnego miesiaca)
        annual_estimate = prev_sales_net * 12
        tier = get_zus_tier(annual_estimate)
        snap.estimated_zus = tier.monthly_contribution

        snap.reminders = self._build_reminders(
            prev_month, prev_year, snap.estimated_ryczalt, snap.estimated_zus
        )
        snap.reminders.extend(self._invoice_reminders(snap.overdue_invoices, snap.unpaid_invoices))
        snap.reminders.sort(key=lambda r: r.due_date)
        return snap

    def _sum_invoices(self, records: list[InvoiceRecord], year: int, month: int) -> tuple[Decimal, Decimal]:
        filtered = [r for r in records if r.issue_date.year == year and r.issue_date.month == month]
        net = sum((Decimal(str(r.total_net)) for r in filtered), Decimal("0"))
        vat = sum((Decimal(str(r.total_vat)) for r in filtered), Decimal("0"))
        return net, vat

    def _sum_expenses(self, records: list[ExpenseRecord], year: int, month: int) -> tuple[Decimal, Decimal]:
        filtered = [
            r for r in records
            if r.receive_date.year == year and r.receive_date.month == month and r.vat_deductible
        ]
        net = sum((Decimal(str(r.total_net)) for r in filtered), Decimal("0"))
        vat = sum((Decimal(str(r.total_vat)) for r in filtered), Decimal("0"))
        return net, vat

    def _build_reminders(
        self,
        prev_month: int,
        prev_year: int,
        ryczalt: Decimal,
        zus: Decimal,
    ) -> list[Reminder]:
        deadlines = get_tax_deadlines(prev_month, prev_year)
        month_name = f"{prev_month:02d}/{prev_year}"
        items = [
            ("Ryczalt za " + month_name, deadlines["ryczalt"], ryczalt),
            ("ZUS zdrowotne za " + month_name, deadlines["zus_health"], zus),
            ("VAT + JPK_V7M za " + month_name, deadlines["vat_jpk"], None),
        ]
        return [self._make_reminder(label, due, amount) for label, due, amount in items]

    def _invoice_reminders(
        self,
        overdue: list[InvoiceRecord],
        unpaid: list[InvoiceRecord],
    ) -> list[Reminder]:
        reminders: list[Reminder] = []
        for inv in overdue:
            days = (inv.payment_due - self.today).days
            reminders.append(Reminder(
                label=f"Faktura {inv.number} ({inv.buyer_name}) — PO TERMINIE",
                due_date=inv.payment_due,
                amount=Decimal(str(inv.total_gross)),
                level=ReminderLevel.OVERDUE,
                days_until=days,
            ))
        for inv in unpaid:
            days = (inv.payment_due - self.today).days
            if days <= 7:
                reminders.append(Reminder(
                    label=f"Faktura {inv.number} ({inv.buyer_name})",
                    due_date=inv.payment_due,
                    amount=Decimal(str(inv.total_gross)),
                    level=self._level_for(days),
                    days_until=days,
                ))
        return reminders

    def _make_reminder(self, label: str, due: date, amount: Decimal | None) -> Reminder:
        days = (due - self.today).days
        return Reminder(
            label=label, due_date=due, amount=amount,
            level=self._level_for(days), days_until=days,
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
