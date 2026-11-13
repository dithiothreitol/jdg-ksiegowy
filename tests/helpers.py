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


def seed_parity_dataset() -> None:
    """Staly zestaw danych dla testu parytetu stare skrypty <-> `jdg` (tests/golden)."""
    rows = [
        InvoiceRow(
            number="A1/09/2026",
            issue_date=date(2026, 10, 1),
            sale_date=date(2026, 9, 30),
            payment_due=date(2026, 10, 15),
            total_net=Decimal("10000"),
            paid_at=datetime(2026, 10, 14),
            status="paid",
        ),
        InvoiceRow(
            number="A1/10/2026",
            issue_date=date(2026, 10, 31),
            total_net=Decimal("10500"),
            payment_due=date(2026, 11, 14),
        ),
        InvoiceRow(
            number="A2/10/2026",
            issue_date=date(2026, 10, 15),
            total_net=Decimal("333.33"),
            vat_rate=Decimal("8"),
            payment_due=date(2026, 11, 20),
        ),
    ]
    for row in rows:
        save_invoice(row)
    expenses = [
        ExpenseRow(
            id="e-pl",
            issue_date=date(2026, 10, 3),
            receive_date=date(2026, 10, 5),
            total_net=Decimal("100"),
            total_vat=Decimal("23"),
            document_number="FV/1",
        ),
        ExpenseRow(
            id="e-fuel",
            issue_date=date(2026, 10, 7),
            total_net=Decimal("200"),
            total_vat=Decimal("46"),
            category="paliwo",
            vat_deduction_pct=Decimal("50"),
            document_number="FV/2",
        ),
        ExpenseRow(
            id="e-us",
            issue_date=date(2026, 10, 10),
            total_net=Decimal("765.92"),
            total_vat=Decimal("176.16"),
            seller_name="Anthropic PBC",
            seller_nip="",
            seller_country="US",
            reverse_charge=True,
            document_number="INV-1",
        ),
        ExpenseRow(
            id="e-de",
            issue_date=date(2026, 10, 12),
            total_net=Decimal("100"),
            total_vat=Decimal("23"),
            seller_name="Hetzner",
            seller_nip="DE812871812",
            seller_country="DE",
            reverse_charge=True,
            document_number="R-1",
        ),
    ]
    for exp in expenses:
        save_expense(exp)
