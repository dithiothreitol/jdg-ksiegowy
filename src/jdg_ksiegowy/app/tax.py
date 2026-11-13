"""Przypadki uzycia: kalkulacje podatkowe, terminy, PIT-28, skladki ZUS, zaplaty."""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import ClassVar, Literal

from pydantic import BaseModel

from jdg_ksiegowy.app.audit import audit
from jdg_ksiegowy.app.errors import ConfigMissingError, InvalidInputError
from jdg_ksiegowy.config import settings
from jdg_ksiegowy.registry.repository import (
    InvoiceRepository,
    TaxPayment,
    TaxPaymentRepository,
)
from jdg_ksiegowy.tax.deadlines import monthly_deadlines
from jdg_ksiegowy.tax.microaccount import format_nrb, microaccount
from jdg_ksiegowy.tax.obligations import (
    monthly_contributions,
    ryczalt,
    social_mode_on,
)
from jdg_ksiegowy.tax.pit28 import generate_pit28_report
from jdg_ksiegowy.tax.zus import (
    MissingTaxParamsError,
    get_social_contribution,
    get_zus_tier,
)

PaymentKind = Literal["ryczalt", "vat", "zus_health", "zus_social"]


def _params_error(e: MissingTaxParamsError) -> ConfigMissingError:
    return ConfigMissingError(str(e), hint="Parametry ZUS publikuje GUS/ZUS na początku roku.")


def tax_microaccount() -> str | None:
    """Mikrorachunek podatkowy sprzedawcy (PIT/ryczalt, VAT) albo None bez poprawnego NIP."""
    try:
        return format_nrb(microaccount(settings.seller.nip))
    except ValueError:
        return None


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
    tax_microaccount: str | None


def calculate(
    net: Decimal,
    *,
    month: int,
    year: int,
    vat_rate: Decimal | None = None,
    ryczalt_rate: Decimal | None = None,
    annual_revenue: Decimal | None = None,
) -> TaxCalc:
    """VAT, ryczalt i ZUS od kwoty netto — szacunek dla miesiaca (bez odliczen skladek)."""
    vat_rate = settings.seller.vat_rate if vat_rate is None else vat_rate
    ryczalt_rate = settings.seller.ryczalt_rate if ryczalt_rate is None else ryczalt_rate
    vat = (net * vat_rate / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    annual = annual_revenue if annual_revenue else net * 12
    mode = social_mode_on(date(year, month, 1))
    try:
        tier = get_zus_tier(annual, year=year)
        social = get_social_contribution(mode, settings.seller.zus_voluntary_sickness, year=year)
    except MissingTaxParamsError as e:
        raise _params_error(e) from e
    tax = ryczalt(net, Decimal("0"), ryczalt_rate).tax
    deadlines = monthly_deadlines(month, year)
    return TaxCalc(
        net=net,
        vat_rate=vat_rate,
        vat=vat,
        gross=net + vat,
        ryczalt_rate=ryczalt_rate,
        ryczalt=tax,
        zus_health_monthly=tier.monthly_contribution,
        zus_tier=tier.label,
        zus_health_deductible_monthly=(tier.monthly_contribution / 2).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ),
        zus_social_mode=mode.value,
        zus_social_monthly=social,
        zus_total_monthly=tier.monthly_contribution + social,
        estimated_annual_revenue=annual,
        deadline_ryczalt_zus=deadlines["ryczalt"],
        deadline_vat_jpk=deadlines["vat_jpk"],
        total_monthly_burden=tax + tier.monthly_contribution + social + vat,
        tax_microaccount=tax_microaccount(),
    )


class Deadlines(BaseModel):
    period: str
    ryczalt: date
    zus: date
    vat_jpk: date


def deadlines(month: int, year: int) -> Deadlines:
    """Terminy za miesiac rozliczeniowy (przesuniete na dzien roboczy)."""
    d = monthly_deadlines(month, year)
    return Deadlines(period=f"{year}-{month:02d}", ryczalt=d["ryczalt"], zus=d["zus"],
                     vat_jpk=d["vat_jpk"])  # fmt: skip


class Pit28Month(BaseModel):
    month: int
    sales_net: Decimal
    deductions: Decimal
    ryczalt: Decimal


class Pit28View(BaseModel):
    year: int
    ryczalt_rate: Decimal
    annual_sales_net: Decimal
    annual_deductions: Decimal
    annual_base: Decimal
    annual_ryczalt: Decimal
    advances_paid: Decimal
    to_pay: Decimal
    deadline: date
    monthly: list[Pit28Month]


def pit28(year: int) -> Pit28View:
    r = generate_pit28_report(year)
    return Pit28View(
        year=r.year,
        ryczalt_rate=r.ryczalt_rate,
        annual_sales_net=r.annual_sales_net,
        annual_deductions=r.annual_deductions,
        annual_base=r.annual_base,
        annual_ryczalt=r.annual_ryczalt,
        advances_paid=r.advances_paid,
        to_pay=r.to_pay,
        deadline=r.deadline,
        monthly=[
            Pit28Month(
                month=m.month, sales_net=m.sales_net, deductions=m.deductions, ryczalt=m.ryczalt
            )
            for m in r.monthly
            if m.sales_net
        ],  # fmt: skip
    )


class ZusView(BaseModel):
    period: str
    revenue_ytd: Decimal
    health_tier: str
    health: Decimal
    social_mode: str
    social: Decimal
    total: Decimal
    deadline: date
    how_to_file: str


def zus(month: int, year: int) -> ZusView:
    """Skladki za miesiac: zdrowotna wg przychodu narastajaco z rejestru + spoleczne."""
    try:
        c = monthly_contributions(
            InvoiceRepository().list(),
            TaxPaymentRepository().list(),
            year,
            month,
            social_mode=social_mode_on(date(year, month, 1)),
            voluntary_sickness=settings.seller.zus_voluntary_sickness,
        )
    except MissingTaxParamsError as e:
        raise _params_error(e) from e
    return ZusView(
        period=f"{year}-{month:02d}",
        revenue_ytd=c.revenue_ytd,
        health_tier=c.health_tier.label,
        health=c.health,
        social_mode=c.social_mode.value,
        social=c.social,
        total=c.total,
        deadline=monthly_deadlines(month, year)["zus"],
        how_to_file="Deklaracja DRA w PUE/eZUS (lub Płatnik); składki na rachunek ZUS.",
    )


class PaymentView(BaseModel):
    table_columns: ClassVar[tuple[str, ...]] = ("period", "type", "amount", "due_date", "paid_at")

    period: str
    type: str
    amount: Decimal
    due_date: date
    paid_at: datetime | None

    @classmethod
    def of(cls, p: TaxPayment) -> PaymentView:
        return cls(period=f"{p.year}-{p.month:02d}", type=p.type, amount=p.amount,
                   due_date=p.due_date, paid_at=p.paid_at)  # fmt: skip


class PaymentList(BaseModel):
    payments: list[PaymentView]


def record_payment(
    kind: PaymentKind, year: int, month: int, amount: Decimal, paid_on: date | None = None
) -> PaymentView:
    """Zapisz zaplate podatku/skladki — gasi przypomnienie i wchodzi do odliczen."""
    if amount <= 0:
        raise InvalidInputError("Kwota zapłaty musi być dodatnia")
    due_key = "zus" if kind.startswith("zus") else ("vat_jpk" if kind == "vat" else "ryczalt")
    payment = TaxPayment(
        type=kind,
        year=year,
        month=month,
        amount=amount,
        due_date=monthly_deadlines(month, year)[due_key],
        paid_at=datetime.combine(paid_on or date.today(), datetime.min.time()),
    )
    TaxPaymentRepository().record(payment)
    audit("tax.pay", f"{kind} {year}-{month:02d}", "ok", {"amount": str(amount)})
    return PaymentView.of(payment)


def list_payments(year: int | None = None) -> PaymentList:
    return PaymentList(payments=[PaymentView.of(p) for p in TaxPaymentRepository().list(year=year)])
