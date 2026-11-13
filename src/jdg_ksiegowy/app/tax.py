"""Przypadki uzycia: kalkulacje podatkowe, terminy, PIT-28, DRA ZUS."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from pydantic import BaseModel

from jdg_ksiegowy.config import DATA_DIR, settings
from jdg_ksiegowy.invoice.calculator import get_tax_deadlines
from jdg_ksiegowy.tax.pit28 import generate_pit28_report
from jdg_ksiegowy.tax.zus import (
    ZUSSocialMode,
    get_current_social_mode,
    get_social_contribution,
    get_zus_tier,
)
from jdg_ksiegowy.zus.dra import DRARequest, dra_deadline, generate_dra_xml

_CENT = Decimal("0.01")


def _pct(value: Decimal, rate: Decimal) -> Decimal:
    return (value * rate / 100).quantize(_CENT, rounding=ROUND_HALF_UP)


def _social_mode(today: date) -> ZUSSocialMode:
    seller = settings.seller
    raw = seller.zus_social_mode
    return get_current_social_mode(
        today=today,
        business_start=(
            date.fromisoformat(seller.business_start_date) if seller.business_start_date else None
        ),
        employment_above_min=seller.employment_gross_above_min,
        override=None if not raw or raw == "auto" else ZUSSocialMode(raw),
    )


class TaxCalc(BaseModel):
    net: Decimal
    vat_rate: Decimal
    vat: Decimal
    gross: Decimal
    ryczalt_rate: Decimal
    ryczalt: Decimal
    zus_health_monthly: Decimal
    zus_tier: str
    zus_health_deductible_monthly: Decimal
    zus_social_mode: str
    zus_social_monthly: Decimal
    zus_total_monthly: Decimal
    estimated_annual_revenue: Decimal
    deadline_ryczalt_zus: date
    deadline_vat_jpk: date
    total_monthly_burden: Decimal


def calculate(
    net: Decimal,
    *,
    month: int,
    year: int,
    vat_rate: Decimal | None = None,
    ryczalt_rate: Decimal | None = None,
    annual_revenue: Decimal | None = None,
) -> TaxCalc:
    """VAT, ryczalt i ZUS od kwoty netto (szacunek miesieczny)."""
    vat_rate = settings.seller.vat_rate if vat_rate is None else vat_rate
    ryczalt_rate = settings.seller.ryczalt_rate if ryczalt_rate is None else ryczalt_rate
    vat = _pct(net, vat_rate)
    ryczalt = _pct(net, ryczalt_rate)
    annual = annual_revenue if annual_revenue else net * 12
    tier = get_zus_tier(annual)
    mode = _social_mode(date(year, month, 1))
    social = get_social_contribution(
        mode, voluntary_sickness=settings.seller.zus_voluntary_sickness
    )
    deadlines = get_tax_deadlines(month, year)
    return TaxCalc(
        net=net,
        vat_rate=vat_rate,
        vat=vat,
        gross=net + vat,
        ryczalt_rate=ryczalt_rate,
        ryczalt=ryczalt,
        zus_health_monthly=tier.monthly_contribution,
        zus_tier=tier.label,
        zus_health_deductible_monthly=_pct(tier.monthly_contribution, Decimal("50")),
        zus_social_mode=mode.value,
        zus_social_monthly=social,
        zus_total_monthly=tier.monthly_contribution + social,
        estimated_annual_revenue=annual,
        deadline_ryczalt_zus=deadlines["ryczalt"],
        deadline_vat_jpk=deadlines["vat_jpk"],
        total_monthly_burden=ryczalt + tier.monthly_contribution + social + vat,
    )


class Deadlines(BaseModel):
    period: str
    ryczalt: date
    zus: date
    vat_jpk: date


def deadlines(month: int, year: int) -> Deadlines:
    """Terminy platnosci i deklaracji za miesiac rozliczeniowy."""
    d = get_tax_deadlines(month, year)
    return Deadlines(
        period=f"{year}-{month:02d}",
        ryczalt=d["ryczalt"],
        zus=d["zus_health"],
        vat_jpk=d["vat_jpk"],
    )


class Pit28Month(BaseModel):
    month: int
    sales_net: Decimal
    ryczalt: Decimal


class Pit28View(BaseModel):
    year: int
    ryczalt_rate: Decimal
    annual_sales_net: Decimal
    annual_ryczalt: Decimal
    annual_ryczalt_rounded: Decimal
    monthly: list[Pit28Month]


def pit28(year: int) -> Pit28View:
    report = generate_pit28_report(year)
    return Pit28View(
        year=report.year,
        ryczalt_rate=report.ryczalt_rate,
        annual_sales_net=report.annual_sales_net,
        annual_ryczalt=report.annual_ryczalt,
        annual_ryczalt_rounded=report.annual_ryczalt_rounded,
        monthly=[
            Pit28Month(month=m.month, sales_net=m.sales_net, ryczalt=m.ryczalt)
            for m in report.monthly
            if m.sales_net > 0
        ],
    )


class DraView(BaseModel):
    period: str
    xml_path: str
    health_contribution: Decimal
    social_contribution: Decimal
    total: Decimal
    deadline: date
    how_to_send: str


def dra(
    month: int,
    year: int,
    *,
    annual_prior_income: Decimal,
    include_social: bool = False,
    output: Path | None = None,
) -> DraView:
    result = generate_dra_xml(
        DRARequest(
            month=month,
            year=year,
            annual_prior_income=annual_prior_income,
            include_social=include_social,
        )
    )
    path = output or DATA_DIR / "zus" / f"DRA_{month:02d}_{year}.xml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.xml, encoding="utf-8")
    return DraView(
        period=f"{year}-{month:02d}",
        xml_path=str(path),
        health_contribution=result.health_contribution,
        social_contribution=result.social_contribution,
        total=result.total,
        deadline=dra_deadline(month, year),
        how_to_send="PUE ZUS > Dokumenty i wiadomosci > Import KEDU — wskaz wygenerowany plik.",
    )
