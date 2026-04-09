"""Modele danych faktur i kontrahentow."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    GENERATED = "generated"
    SENT_KSEF = "sent_ksef"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class OfferStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class SendChannel(StrEnum):
    EMAIL = "email"
    WHATSAPP = "whatsapp"


class Buyer(BaseModel):
    """Dane nabywcy (kontrahenta)."""

    name: str
    nip: str
    address: str
    email: str | None = None
    country_code: str = "PL"


class LineItem(BaseModel):
    """Pozycja na fakturze."""

    description: str
    quantity: Decimal = Decimal("1")
    unit: str = "usl."
    unit_price_net: Decimal
    vat_rate: Decimal = Decimal("23")

    @computed_field
    @property
    def net_value(self) -> Decimal:
        return round(self.quantity * self.unit_price_net, 2)

    @computed_field
    @property
    def vat_amount(self) -> Decimal:
        return round(self.net_value * self.vat_rate / 100, 2)

    @computed_field
    @property
    def gross_value(self) -> Decimal:
        return round(self.net_value + self.vat_amount, 2)


class InvoiceCalc(BaseModel):
    """Wynik kalkulacji podatkowej faktury."""

    netto: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    brutto: Decimal
    ryczalt_rate: Decimal
    ryczalt_amount: Decimal


class Invoice(BaseModel):
    """Pelny model faktury."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    number: str  # np. "A1/04/2026"
    issue_date: date
    sale_date: date
    period_from: date | None = None
    period_to: date | None = None
    payment_due: date
    buyer: Buyer
    items: list[LineItem]
    status: InvoiceStatus = InvoiceStatus.DRAFT
    ksef_reference: str | None = None
    ksef_sent_at: datetime | None = None
    notes: str | None = None

    @computed_field
    @property
    def total_net(self) -> Decimal:
        return sum(item.net_value for item in self.items)

    @computed_field
    @property
    def total_vat(self) -> Decimal:
        return sum(item.vat_amount for item in self.items)

    @computed_field
    @property
    def total_gross(self) -> Decimal:
        return sum(item.gross_value for item in self.items)


class Contract(BaseModel):
    """Kontrakt cykliczny — definicja automatycznej faktury."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    buyer: Buyer
    description: str  # opis uslugi na fakturze
    net_amount: Decimal
    vat_rate: Decimal = Decimal("23")
    cycle: str = "monthly"  # monthly | quarterly
    day_of_month: int = -1  # -1 = ostatni dzien roboczy
    auto_send_ksef: bool = True
    auto_send_email: bool = True
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
