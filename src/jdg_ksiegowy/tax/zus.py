"""Skladki ZUS dla ryczaltowcow (2026).

Zdrowotna: progi wg rocznego przychodu (9% × podstawa).
Podstawa: przecietne wynagrodzenie Q4 2025 = 9228.64 PLN (GUS, 22.01.2026).

Spoleczne: 4 tryby wyboru — zaleznie od stazu dzialalnosci i zbiegu z UoP.
Zrodlo: zus.pl (styczen 2026). Prognozowane przecietne 2026: 9420 PLN,
minimum wynagrodzenie 2026: 4806 PLN.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


# -------------------- SKLADKA ZDROWOTNA (ryczalt, progi) --------------------

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
    """Zwroc prog zdrowotnej na podstawie rocznego przychodu."""
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


# -------------------- SKLADKI SPOLECZNE (4 tryby) --------------------

class ZUSSocialMode(StrEnum):
    """Tryb rozliczenia skladek spolecznych."""

    START_RELIEF = "start_relief"   # Ulga na start, 6 mies od rozpoczecia
    SMALL_ZUS = "small_zus"         # Preferencyjne, 24 mies po uldze (30% min. wyn.)
    EMPLOYMENT = "employment"       # Zbieg z UoP >= min. wyn. — brak spolecznych z JDG
    FULL = "full"                   # Pelne (60% prognozowanego przecietnego)


@dataclass(frozen=True)
class ZUSSocialTier:
    mode: ZUSSocialMode
    monthly_contribution: Decimal  # BEZ dobrowolnej chorobowej
    sickness_optional: Decimal     # kwota chorobowej (do doliczenia gdy dobrowolna)
    label: str
    kedu_code: str                 # kod tytulu ubezpieczenia (KEDU)


# Wartosci 2026 (bez chorobowej dobrowolnej). Z chorobowa: dodac sickness_optional.
ZUS_SOCIAL_TIERS_2026: dict[ZUSSocialMode, ZUSSocialTier] = {
    ZUSSocialMode.START_RELIEF: ZUSSocialTier(
        mode=ZUSSocialMode.START_RELIEF,
        monthly_contribution=Decimal("0.00"),
        sickness_optional=Decimal("0.00"),
        label="Ulga na start (6 mies, 0 PLN spolecznych)",
        kedu_code="0540",
    ),
    ZUSSocialMode.SMALL_ZUS: ZUSSocialTier(
        mode=ZUSSocialMode.SMALL_ZUS,
        monthly_contribution=Decimal("420.86"),
        sickness_optional=Decimal("35.32"),
        label="Preferencyjne 24 mies (30% min. wyn.)",
        kedu_code="0570",
    ),
    ZUSSocialMode.EMPLOYMENT: ZUSSocialTier(
        mode=ZUSSocialMode.EMPLOYMENT,
        monthly_contribution=Decimal("0.00"),
        sickness_optional=Decimal("0.00"),
        label="Zbieg z UoP (tylko zdrowotna)",
        kedu_code="0510",
    ),
    ZUSSocialMode.FULL: ZUSSocialTier(
        mode=ZUSSocialMode.FULL,
        monthly_contribution=Decimal("1788.29"),
        sickness_optional=Decimal("138.47"),
        label="Pelne (60% prognozowanego przecietnego)",
        kedu_code="0510",
    ),
}


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    year = d.year + m // 12
    month = m % 12 + 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def get_current_social_mode(
    today: date,
    business_start: date | None,
    employment_above_min: bool,
    override: ZUSSocialMode | None = None,
) -> ZUSSocialMode:
    """Wybierz tryb spolecznych wg priorytetu: override > employment > staz > full.

    - override: recznie wymuszony tryb (z .env)
    - employment_above_min: UoP z brutto >= min. wyn. -> brak spolecznych z JDG
    - business_start: data rozpoczecia/wznowienia — decyduje o start_relief / small_zus
    """
    if override is not None:
        return override
    if employment_above_min:
        return ZUSSocialMode.EMPLOYMENT
    if business_start is None:
        return ZUSSocialMode.FULL

    start_relief_end = _add_months(business_start, 6)
    small_zus_end = _add_months(start_relief_end, 24)

    if today < start_relief_end:
        return ZUSSocialMode.START_RELIEF
    if today < small_zus_end:
        return ZUSSocialMode.SMALL_ZUS
    return ZUSSocialMode.FULL


def get_social_contribution(
    mode: ZUSSocialMode, voluntary_sickness: bool = False
) -> Decimal:
    """Miesieczna skladka spoleczna dla trybu (opcjonalnie + chorobowa)."""
    tier = ZUS_SOCIAL_TIERS_2026[mode]
    return tier.monthly_contribution + (tier.sickness_optional if voluntary_sickness else Decimal("0"))


def get_total_monthly_zus(
    annual_revenue: Decimal,
    mode: ZUSSocialMode,
    voluntary_sickness: bool = False,
) -> Decimal:
    """Calkowita miesieczna skladka ZUS = spoleczne + zdrowotna."""
    return get_social_contribution(mode, voluntary_sickness) + get_monthly_zus(annual_revenue)
