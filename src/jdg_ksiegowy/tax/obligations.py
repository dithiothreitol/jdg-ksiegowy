"""Zobowiazania miesieczne ryczaltowca: ryczalt, skladki ZUS — czysta logika, bez bazy.

- Przychod miesiaca wg daty uzyskania przychodu (art. 14 ust. 1c ustawy o PIT).
- Ryczalt: (przychod - zaplacone w miesiacu skladki spoleczne - 50% zaplaconej zdrowotnej)
  x stawka; podstawa i podatek zaokraglane do pelnych zlotych (art. 63 Ordynacji).
- Zdrowotna: prog wg przychodu narastajaco od poczatku roku pomniejszonego o zaplacone
  skladki spoleczne; od miesiaca przekroczenia progu obowiazuje wyzsza skladka.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from jdg_ksiegowy.invoice.models import Invoice
from jdg_ksiegowy.registry.repository import TaxPayment
from jdg_ksiegowy.tax.income import income_date
from jdg_ksiegowy.tax.rounding import round_pln
from jdg_ksiegowy.tax.zus import (
    ZUSHealthTier,
    ZUSSocialMode,
    get_social_contribution,
    get_zus_tier,
)

ZERO = Decimal("0")
HEALTH_DEDUCTIBLE_SHARE = Decimal("0.5")


def revenue(invoices: Iterable[Invoice], year: int, month: int | None = None) -> Decimal:
    """Przychod netto z faktur (z korektami) w roku lub miesiacu uzyskania przychodu."""
    return sum(
        (
            i.total_net
            for i in invoices
            if (d := income_date(i)).year == year and (month is None or d.month == month)
        ),
        ZERO,
    )


def paid_in(
    payments: Iterable[TaxPayment], kind: str, year: int, month: int | None = None
) -> Decimal:
    """Suma zaplat danego rodzaju, ktore WPLYNELY w okresie (wg daty zaplaty)."""
    return sum(
        (
            p.amount
            for p in payments
            if p.type == kind
            and p.paid_at is not None
            and p.paid_at.year == year
            and (month is None or p.paid_at.month == month)
        ),
        ZERO,
    )


@dataclass(frozen=True)
class Ryczalt:
    revenue: Decimal
    deductions: Decimal  # spoleczne + 50% zdrowotnej zaplacone w okresie
    base: Decimal  # zaokraglona do zl
    rate: Decimal
    tax: Decimal  # zaokraglony do zl


def ryczalt(revenue_amount: Decimal, deductions: Decimal, rate: Decimal) -> Ryczalt:
    base = round_pln(max(revenue_amount - deductions, ZERO))
    return Ryczalt(
        revenue=revenue_amount,
        deductions=deductions,
        base=base,
        rate=rate,
        tax=round_pln(base * rate / 100),
    )


def deductions_paid(payments: Iterable[TaxPayment], year: int, month: int | None) -> Decimal:
    payments = list(payments)
    social = paid_in(payments, "zus_social", year, month)
    health = paid_in(payments, "zus_health", year, month)
    return social + (health * HEALTH_DEDUCTIBLE_SHARE).quantize(Decimal("0.01"))


def monthly_ryczalt(
    invoices: Iterable[Invoice],
    payments: Iterable[TaxPayment],
    year: int,
    month: int,
    rate: Decimal,
) -> Ryczalt:
    return ryczalt(revenue(invoices, year, month), deductions_paid(payments, year, month), rate)


@dataclass(frozen=True)
class Contributions:
    year: int
    month: int
    revenue_ytd: Decimal  # przychod narastajaco pomniejszony o zaplacone spoleczne
    health_tier: ZUSHealthTier
    health: Decimal
    social_mode: ZUSSocialMode
    social: Decimal

    @property
    def total(self) -> Decimal:
        return self.health + self.social


def monthly_contributions(
    invoices: Iterable[Invoice],
    payments: Iterable[TaxPayment],
    year: int,
    month: int,
    *,
    social_mode: ZUSSocialMode,
    voluntary_sickness: bool,
) -> Contributions:
    invoices, payments = list(invoices), list(payments)
    ytd = sum((revenue(invoices, year, m) for m in range(1, month + 1)), ZERO)
    social_paid = sum((paid_in(payments, "zus_social", year, m) for m in range(1, month + 1)), ZERO)
    basis = max(ytd - social_paid, ZERO)
    tier = get_zus_tier(basis, year=year)
    return Contributions(
        year=year,
        month=month,
        revenue_ytd=basis,
        health_tier=tier,
        health=tier.monthly_contribution,
        social_mode=social_mode,
        social=get_social_contribution(social_mode, voluntary_sickness, year=year),
    )


def social_mode_on(day: date) -> ZUSSocialMode:
    """Tryb skladek spolecznych z konfiguracji sprzedawcy na dany dzien."""
    from jdg_ksiegowy.config import settings
    from jdg_ksiegowy.tax.zus import get_current_social_mode

    seller = settings.seller
    raw = seller.zus_social_mode
    return get_current_social_mode(
        today=day,
        business_start=(
            date.fromisoformat(seller.business_start_date) if seller.business_start_date else None
        ),
        employment_above_min=seller.employment_gross_above_min,
        override=None if not raw or raw == "auto" else ZUSSocialMode(raw),
    )
