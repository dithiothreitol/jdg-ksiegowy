"""Modele danych faktur i kontrahentow."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field, field_validator

from jdg_ksiegowy.validators import validate_nip


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
    nip: str = ""
    address: str
    email: str | None = None
    country_code: str = "PL"
    eu_vat_number: str | None = None  # numer VAT-UE, np. "DE123456789"

    @field_validator("nip")
    @classmethod
    def nip_must_be_valid(cls, v: str) -> str:
        import re

        digits = re.sub(r"[\s\-]", "", v)
        if re.fullmatch(r"\d{10}", digits) and not validate_nip(digits):
            raise ValueError(f"Nieprawidlowy NIP: {v!r}")
        return digits

    def identifier_for_xml(self) -> tuple[str, str]:
        """Zwróć (typ, wartość) identyfikatora do FA(3)/JPK.

        Typy: "NIP" | "NrVatUE" | "BrakID"
        """
        if self.nip and self.country_code == "PL":
            return ("NIP", self.nip)
        if self.eu_vat_number:
            return ("NrVatUE", self.eu_vat_number)
        return ("BrakID", "")

    def best_identifier(self) -> str:
        """Najlepszy identyfikator do pól tekstowych (NrKontrahenta w JPK)."""
        id_type, value = self.identifier_for_xml()
        if id_type == "BrakID":
            return "BRAK"
        return value


class LineItem(BaseModel):
    """Pozycja na fakturze."""

    description: str
    quantity: Decimal = Decimal("1")
    unit: str = "usl."
    unit_price_net: Decimal
    vat_rate: Decimal = Decimal("23")
    vat_code: str | None = None  # override P_12 w FA(3): "NP", "ZW", "0" itp.

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
        return sum((item.net_value for item in self.items), Decimal("0"))

    @computed_field
    @property
    def total_vat(self) -> Decimal:
        return sum((item.vat_amount for item in self.items), Decimal("0"))

    @computed_field
    @property
    def total_gross(self) -> Decimal:
        return sum((item.gross_value for item in self.items), Decimal("0"))

    def totals_by_vat_rate(self) -> dict[Decimal, tuple[Decimal, Decimal]]:
        """Sumy (netto, vat) zgrupowane po stawce VAT (Decimal)."""
        buckets: dict[Decimal, tuple[Decimal, Decimal]] = {}
        for item in self.items:
            net, vat = buckets.get(item.vat_rate, (Decimal("0"), Decimal("0")))
            buckets[item.vat_rate] = (net + item.net_value, vat + item.vat_amount)
        return buckets


class CorrectionReason(StrEnum):
    """Powód korekty faktury wg FA(3)."""

    PRICE_CHANGE = "01"  # zmiana ceny / rabat
    RETURN_GOODS = "02"  # zwrot towaru / odstąpienie
    OTHER = "99"  # inne


class InvoiceCorrection(BaseModel):
    """Faktura korygująca (FA KOR) wg FA(3).

    Koryguje wcześniej wystawioną fakturę. Zawiera dane różnicowe
    (pozycje ze zmienionymi kwotami — ujemnymi przy zmniejszeniu).
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    number: str  # numer korekty, np. "AK1/04/2026"
    original_number: str  # numer korygowanej faktury
    original_ksef_reference: str | None = None
    issue_date: date
    correction_date: date  # data wystawienia korekty
    buyer: Buyer
    items: list[LineItem]  # pozycje różnicowe (ujemne = zmniejszenie)
    reason: CorrectionReason = CorrectionReason.OTHER
    reason_description: str = ""  # opis słowny powodu korekty
    notes: str | None = None

    @computed_field
    @property
    def total_net(self) -> Decimal:
        return sum((item.net_value for item in self.items), Decimal("0"))

    @computed_field
    @property
    def total_vat(self) -> Decimal:
        return sum((item.vat_amount for item in self.items), Decimal("0"))

    @computed_field
    @property
    def total_gross(self) -> Decimal:
        return sum((item.gross_value for item in self.items), Decimal("0"))


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
