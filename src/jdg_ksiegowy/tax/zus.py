"""Skladki ZUS przedsiebiorcy na ryczalcie — parametry per rok.

Zdrowotna: prog wg przychodu NARASTAJACO od poczatku roku (pomniejszonego o zaplacone
skladki spoleczne); po przekroczeniu progu wyzsza skladka obowiazuje od miesiaca
przekroczenia. Spoleczne: tryb zalezny od stazu dzialalnosci i zbiegu z umowa o prace.

Parametry na nowy rok publikuja GUS/ZUS (przecietne wynagrodzenie za IV kw. — styczen,
prognozowane przecietne i placa minimalna — ustawa budzetowa). Brak roku w `PARAMS`
konczy sie bledem, a nie cichym uzyciem stawek z poprzedniego roku.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


class ZUSSocialMode(StrEnum):
    START_RELIEF = "start_relief"  # ulga na start: 6 mies. bez skladek spolecznych
    SMALL_ZUS = "small_zus"  # preferencyjne: 24 mies. po uldze (30% placy minimalnej)
    EMPLOYMENT = "employment"  # zbieg z umowa o prace >= placa minimalna
    FULL = "full"  # pelne (60% prognozowanego przecietnego wynagrodzenia)


@dataclass(frozen=True)
class ZUSHealthTier:
    max_annual_revenue: Decimal  # gorna granica progu (wlacznie)
    basis_percent: int  # % przecietnego wynagrodzenia
    monthly_basis: Decimal
    monthly_contribution: Decimal
    label: str


@dataclass(frozen=True)
class ZUSSocialTier:
    mode: ZUSSocialMode
    monthly_contribution: Decimal  # bez dobrowolnej chorobowej
    sickness_optional: Decimal
    label: str
    kedu_code: str  # kod tytulu ubezpieczenia


@dataclass(frozen=True)
class YearParams:
    year: int
    source: str
    health_tiers: tuple[ZUSHealthTier, ...]
    social: dict[ZUSSocialMode, ZUSSocialTier]


_UNLIMITED = Decimal("999999999")

PARAMS: dict[int, YearParams] = {
    2026: YearParams(
        year=2026,
        source=(
            "Przecietne wynagrodzenie IV kw. 2025: 9228.64 zl (GUS, 22.01.2026); "
            "prognozowane 2026: 9420 zl; placa minimalna 2026: 4806 zl"
        ),
        health_tiers=(
            ZUSHealthTier(
                Decimal("60000"), 60, Decimal("5537.18"), Decimal("498.35"), "do 60 000 PLN"
            ),
            ZUSHealthTier(
                Decimal("300000"),
                100,
                Decimal("9228.64"),
                Decimal("830.58"),
                "60 001 - 300 000 PLN",
            ),
            ZUSHealthTier(
                _UNLIMITED, 180, Decimal("16611.55"), Decimal("1495.04"), "powyzej 300 000 PLN"
            ),
        ),  # fmt: skip
        social={
            ZUSSocialMode.START_RELIEF: ZUSSocialTier(
                ZUSSocialMode.START_RELIEF,
                Decimal("0.00"),
                Decimal("0.00"),
                "Ulga na start (6 mies, 0 PLN spolecznych)",
                "0540",
            ),
            ZUSSocialMode.SMALL_ZUS: ZUSSocialTier(
                ZUSSocialMode.SMALL_ZUS,
                Decimal("420.86"),
                Decimal("35.32"),
                "Preferencyjne 24 mies (30% min. wyn.)",
                "0570",
            ),
            ZUSSocialMode.EMPLOYMENT: ZUSSocialTier(
                ZUSSocialMode.EMPLOYMENT,
                Decimal("0.00"),
                Decimal("0.00"),
                "Zbieg z UoP (tylko zdrowotna)",
                "0510",
            ),
            ZUSSocialMode.FULL: ZUSSocialTier(
                ZUSSocialMode.FULL,
                Decimal("1788.29"),
                Decimal("138.47"),
                "Pelne (60% prognozowanego przecietnego)",
                "0510",
            ),
        },  # fmt: skip
    ),
}


class MissingTaxParamsError(LookupError):
    """Brak parametrow ZUS na dany rok — trzeba je dopisac po publikacji."""


def params_for(year: int) -> YearParams:
    try:
        return PARAMS[year]
    except KeyError:
        known = ", ".join(map(str, sorted(PARAMS)))
        raise MissingTaxParamsError(
            f"Brak parametrow ZUS na {year} (znane lata: {known}). Dopisz je w "
            "jdg_ksiegowy/tax/zus.py po publikacji przez GUS/ZUS."
        ) from None


def get_zus_tier(annual_revenue: Decimal, *, year: int) -> ZUSHealthTier:
    """Prog skladki zdrowotnej dla przychodu (narastajaco) w danym roku."""
    tiers = params_for(year).health_tiers
    return next((t for t in tiers if annual_revenue <= t.max_annual_revenue), tiers[-1])


def get_monthly_zus(annual_revenue: Decimal, *, year: int) -> Decimal:
    return get_zus_tier(annual_revenue, year=year).monthly_contribution


def get_social_contribution(
    mode: ZUSSocialMode, voluntary_sickness: bool = False, *, year: int
) -> Decimal:
    tier = params_for(year).social[mode]
    return tier.monthly_contribution + (tier.sickness_optional if voluntary_sickness else 0)


def get_total_monthly_zus(
    annual_revenue: Decimal, mode: ZUSSocialMode, voluntary_sickness: bool = False, *, year: int
) -> Decimal:
    return get_social_contribution(mode, voluntary_sickness, year=year) + get_monthly_zus(
        annual_revenue, year=year
    )


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    year = d.year + m // 12
    month = m % 12 + 1
    return date(year, month, min(d.day, monthrange(year, month)[1]))


def get_current_social_mode(
    today: date,
    business_start: date | None,
    employment_above_min: bool,
    override: ZUSSocialMode | None = None,
) -> ZUSSocialMode:
    """Tryb skladek spolecznych: override > zbieg z UoP > staz dzialalnosci > pelne."""
    if override is not None:
        return override
    if employment_above_min:
        return ZUSSocialMode.EMPLOYMENT
    if business_start is None:
        return ZUSSocialMode.FULL
    start_relief_end = _add_months(business_start, 6)
    if today < start_relief_end:
        return ZUSSocialMode.START_RELIEF
    if today < _add_months(start_relief_end, 24):
        return ZUSSocialMode.SMALL_ZUS
    return ZUSSocialMode.FULL
