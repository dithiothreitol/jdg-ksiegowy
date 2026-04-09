"""Skladki ZUS dla ryczaltowcow (2026).

Zrodlo: https://www.zus.pl/ — skladka zdrowotna na ryczalcie
Podstawa: przecietne wynagrodzenie Q4 2025 = 9228.64 PLN (GUS, 22.01.2026)
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ZUSHealthTier:
    """Prog skladki zdrowotnej."""

    max_annual_revenue: Decimal
    basis_percent: int  # % przecietnego wynagrodzenia
    monthly_basis: Decimal
    monthly_contribution: Decimal
    label: str


AVERAGE_SALARY_Q4_2025 = Decimal("9228.64")
HEALTH_RATE = Decimal("0.09")  # 9%

ZUS_TIERS_2026: list[ZUSHealthTier] = [
    ZUSHealthTier(
        max_annual_revenue=Decimal("60000"),
        basis_percent=60,
        monthly_basis=Decimal("5537.18"),
        monthly_contribution=Decimal("498.35"),
        label="do 60 000 PLN",
    ),
    ZUSHealthTier(
        max_annual_revenue=Decimal("300000"),
        basis_percent=100,
        monthly_basis=Decimal("9228.64"),
        monthly_contribution=Decimal("830.58"),
        label="60 001 - 300 000 PLN",
    ),
    ZUSHealthTier(
        max_annual_revenue=Decimal("999999999"),
        basis_percent=180,
        monthly_basis=Decimal("16611.55"),
        monthly_contribution=Decimal("1495.04"),
        label="powyzej 300 000 PLN",
    ),
]


def get_zus_tier(annual_revenue: Decimal) -> ZUSHealthTier:
    """Zwroc prog ZUS na podstawie rocznego przychodu."""
    for tier in ZUS_TIERS_2026:
        if annual_revenue <= tier.max_annual_revenue:
            return tier
    return ZUS_TIERS_2026[-1]


def get_monthly_zus(annual_revenue: Decimal) -> Decimal:
    """Miesieczna skladka zdrowotna."""
    return get_zus_tier(annual_revenue).monthly_contribution


def get_annual_zus(annual_revenue: Decimal) -> Decimal:
    """Roczna skladka zdrowotna (12 * miesieczna)."""
    return get_monthly_zus(annual_revenue) * 12


def get_deductible_zus(annual_revenue: Decimal) -> Decimal:
    """Roczna kwota skladki zdrowotnej do odliczenia od przychodu (50% w 2026)."""
    return get_annual_zus(annual_revenue) * Decimal("0.5")
