"""Modele faktur zakupu (kosztow)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field


class ExpenseCategory(StrEnum):
    """Kategorie kosztow JDG (uproszczone, do raportowania wewnetrznego)."""

    USLUGI_OBCE = "uslugi_obce"  # uslugi konsultingowe, hosting, SaaS
    MATERIALY = "materialy"
    MEDIA = "media"  # prad, gaz, internet, telefon
    PALIWO = "paliwo"
    SAMOCHOD = "samochod"  # serwis, ubezpieczenie OC/AC
    BIURO = "biuro"  # czynsz, art. biurowe
    SPRZET = "sprzet"  # laptop, monitor itp. (nie ST)
    SZKOLENIA = "szkolenia"
    INNE = "inne"


class Expense(BaseModel):
    """Faktura zakupu (koszt)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    seller_name: str
    seller_nip: str
    seller_country: str = "PL"
    document_number: str  # numer faktury sprzedawcy
    issue_date: date
    receive_date: date  # data wplywu - decyduje o miesiacu JPK_V7M
    description: str = ""
    category: ExpenseCategory = ExpenseCategory.INNE
    total_net: Decimal
    total_vat: Decimal
    vat_rate: Decimal = Decimal("23")
    # Procent VAT podlegający odliczeniu (0-100). Default 100 = pełne odliczenie.
    # Auto osobowe użytkowanie mieszane / prywatne służbowo: 50.
    # Reprezentacja, nieusprawiedliwione koszty: 0.
    vat_deduction_pct: Decimal = Field(default=Decimal("100"), ge=0, le=100)
    file_path: str | None = None  # PDF/JPG dowodu
    notes: str | None = None

    @computed_field
    @property
    def total_gross(self) -> Decimal:
        return self.total_net + self.total_vat

    @computed_field
    @property
    def deductible_net(self) -> Decimal:
        """Netto podlegajace odliczeniu (proporcjonalne do vat_deduction_pct)."""
        return (self.total_net * self.vat_deduction_pct / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    @computed_field
    @property
    def deductible_vat(self) -> Decimal:
        """VAT naliczony do odliczenia (proporcjonalny do vat_deduction_pct)."""
        return (self.total_vat * self.vat_deduction_pct / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
