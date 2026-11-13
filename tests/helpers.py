"""Buildery danych testowych: plaskie wiersze -> modele domenowe -> repozytoria."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from jdg_ksiegowy.expenses.models import Expense, ExpenseCategory
from jdg_ksiegowy.invoice.models import Buyer, Invoice, InvoiceStatus, LineItem
from jdg_ksiegowy.registry.repository import ExpenseRepository, InvoiceRepository


@dataclass
class InvoiceRow:
    """Faktura jednopozycyjna opisana sumami — tak jak w testach sprzed repozytoriow."""

    number: str
    issue_date: date
    total_net: Decimal
    sale_date: date | None = None
    payment_due: date | None = None
    id: str | None = None
    buyer_name: str = "Klient"
    buyer_nip: str = "5260250274"
    buyer_address: str = "ul. Testowa 1"
    vat_rate: Decimal = Decimal("23")
    total_vat: Decimal | None = None  # kontrola spojnosci danych testu
    total_gross: Decimal | None = None
    status: str = "generated"
    paid_at: datetime | None = None
    ksef_number: str | None = None
    ksef_reference: str | None = None

    def to_domain(self) -> Invoice:
        extra = {"id": self.id} if self.id else {}
        inv = Invoice(
            **extra,
            number=self.number,
            issue_date=self.issue_date,
            sale_date=self.sale_date or self.issue_date,
            payment_due=self.payment_due or self.issue_date,
            buyer=Buyer(name=self.buyer_name, nip=self.buyer_nip, address=self.buyer_address),
            items=[
                LineItem(
                    description="usluga",
                    unit_price_net=Decimal(self.total_net),
                    vat_rate=self.vat_rate,
                )
            ],
            status=InvoiceStatus(self.status),
            paid_at=self.paid_at,
            ksef_number=self.ksef_number,
            ksef_reference=self.ksef_reference,
        )
        if self.total_vat is not None:
            assert inv.total_vat == Decimal(self.total_vat), "niespojne dane testu: VAT"
        if self.total_gross is not None:
            assert inv.total_gross == Decimal(self.total_gross), "niespojne dane testu: brutto"
        return inv


def save_invoice(row: InvoiceRow) -> Invoice:
    inv = row.to_domain()
    InvoiceRepository().save(inv)
    return inv


@dataclass
class ExpenseRow:
    issue_date: date
    total_net: Decimal
    total_vat: Decimal
    receive_date: date | None = None
    id: str | None = None
    seller_name: str = "Dostawca"
    seller_nip: str = "5260250274"
    seller_country: str = "PL"
    document_number: str = "FV/1"
    category: str = "inne"
    vat_rate: Decimal = Decimal("23")
    vat_deduction_pct: Decimal = Decimal("100")
    reverse_charge: bool = False
    ksef_number: str | None = None
    total_gross: Decimal | None = None  # liczone z netto + VAT

    def to_domain(self) -> Expense:
        extra = {"id": self.id} if self.id else {}
        return Expense(
            **extra,
            seller_name=self.seller_name,
            seller_nip=self.seller_nip,
            seller_country=self.seller_country,
            document_number=self.document_number,
            issue_date=self.issue_date,
            receive_date=self.receive_date or self.issue_date,
            category=ExpenseCategory(self.category),
            total_net=Decimal(self.total_net),
            total_vat=Decimal(self.total_vat),
            vat_rate=self.vat_rate,
            vat_deduction_pct=self.vat_deduction_pct,
            reverse_charge=self.reverse_charge,
            ksef_number=self.ksef_number,
        )


def save_expense(row: ExpenseRow) -> Expense:
    exp = row.to_domain()
    ExpenseRepository().save(exp)
    return exp
