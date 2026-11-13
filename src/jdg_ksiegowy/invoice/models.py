"""Modele danych faktur i kontrahentow."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from jdg_ksiegowy.validators import EU_COUNTRY_CODES, check_ksef_number, validate_nip


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    GENERATED = "generated"
    SENT_KSEF = "sent_ksef"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class InvoiceKind(StrEnum):
    VAT = "VAT"  # faktura podstawowa
    KOR = "KOR"  # faktura korygujaca (pozycje roznicowe, kwoty ujemne = zmniejszenie)


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


# Kody pozycji bez VAT naleznego: poza terytorium, zwolnione, krajowe 0%, WDT, eksport.
VAT_CODES = ("NP", "ZW", "0", "0_WDT", "0_EXP")


def is_article_100_service(buyer_country: str) -> bool:
    """Usluga NP dla nabywcy z innego kraju UE (art. 100 ust. 1 pkt 4): FA(3) "np II", JPK K_12.

    Pozycje NP traktujemy jak uslugi (profil JDG uslugowej); dla nabywcy spoza UE — "np I".
    """
    return buyer_country.upper() in EU_COUNTRY_CODES


class LineItem(BaseModel):
    """Pozycja na fakturze."""

    description: str
    quantity: Decimal = Decimal("1")
    unit: str = "usl."
    unit_price_net: Decimal
    vat_rate: Decimal = Decimal("23")
    # Pozycja bez VAT naleznego: NP (poza terytorium), ZW, 0, 0_WDT, 0_EXP — stawka = 0.
    vat_code: str | None = None
    gtu: str | None = None  # oznaczenie GTU_01..GTU_13 (JPK_V7M)

    @model_validator(mode="after")
    def _no_vat_for_codes(self) -> LineItem:
        if self.vat_code is None and self.vat_rate == 0:
            self.vat_code = "0"  # stawka 0% bez kodu = krajowa 0% (FA(3) "0 KR", JPK K_13)
        if self.vat_code:
            self.vat_code = self.vat_code.upper()
            if self.vat_code not in VAT_CODES:
                raise ValueError(f"Nieznany kod VAT {self.vat_code!r} (dozwolone: {VAT_CODES})")
            self.vat_rate = Decimal("0")
        if self.gtu and not re.fullmatch(r"GTU_(0[1-9]|1[0-3])", self.gtu):
            raise ValueError(f"Nieprawidlowe oznaczenie GTU: {self.gtu!r} (GTU_01..GTU_13)")
        return self

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


class Invoice(BaseModel):
    """Pelny model faktury."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    number: str  # np. "A1/04/2026"
    kind: InvoiceKind = InvoiceKind.VAT
    issue_date: date
    # Data sprzedazy = okres VAT. Dla korekty: zmniejszenie — data korekty,
    # zwiekszenie — data sprzedazy faktury pierwotnej.
    sale_date: date
    period_from: date | None = None
    period_to: date | None = None
    payment_due: date
    buyer: Buyer
    items: list[LineItem]
    status: InvoiceStatus = InvoiceStatus.DRAFT
    # Numer KSeF nadany fakturze — jedyny identyfikator, ktory trafia do JPK (NrKSeF).
    ksef_number: str | None = None
    # Numer referencyjny wysylki w sesji KSeF (techniczny, nie numer KSeF).
    ksef_reference: str | None = None
    ksef_sent_at: datetime | None = None
    ksef_acquired_at: datetime | None = None
    paid_at: datetime | None = None
    docx_path: str | None = None
    xml_path: str | None = None
    notes: str | None = None
    # Tylko korekty (kind=KOR): faktura korygowana i przyczyna
    corrected_number: str | None = None
    corrected_ksef_number: str | None = None
    corrected_issue_date: date | None = None
    correction_reason: str | None = None

    _check_ksef_number = field_validator("ksef_number", "corrected_ksef_number")(check_ksef_number)

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
