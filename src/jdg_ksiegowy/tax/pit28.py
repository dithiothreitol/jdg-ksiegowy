"""Podsumowanie roczne ryczaltu (PIT-28) z rejestru faktur i ewidencji zaplat.

Przychod wg daty uzyskania przychodu; od przychodu odlicza sie zaplacone w roku skladki
spoleczne i 50% zaplaconej skladki zdrowotnej. Ryczalt roczny minus zaplacone zaliczki
za miesiace roku = kwota do zaplaty z zeznaniem (do 30.04 nastepnego roku). Kwoty pomocnicze.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from jdg_ksiegowy.config import settings
from jdg_ksiegowy.registry.repository import InvoiceRepository, TaxPaymentRepository
from jdg_ksiegowy.tax.deadlines import annual_deadlines
from jdg_ksiegowy.tax.obligations import deductions_paid, monthly_ryczalt, revenue, ryczalt

ZERO = Decimal("0")


@dataclass(frozen=True)
class MonthlyBreakdown:
    month: int
    year: int
    sales_net: Decimal
    deductions: Decimal
    ryczalt: Decimal


@dataclass(frozen=True)
class PIT28Report:
    year: int
    seller_name: str
    seller_nip: str
    ryczalt_rate: Decimal
    monthly: list[MonthlyBreakdown]
    annual_sales_net: Decimal
    annual_deductions: Decimal
    annual_base: Decimal
    annual_ryczalt: Decimal
    advances_paid: Decimal  # zaplacone zaliczki za miesiace roku (wg okresu)
    to_pay: Decimal  # ujemne = nadplata
    deadline: date


def generate_pit28_report(year: int) -> PIT28Report:
    invoices = InvoiceRepository().list(year=year, by="income")
    payments = [p for p in TaxPaymentRepository().list() if p.paid_at]
    seller = settings.seller
    rate = seller.ryczalt_rate
    monthly = []
    for m in range(1, 13):
        r = monthly_ryczalt(invoices, payments, year, m, rate)
        monthly.append(MonthlyBreakdown(m, year, r.revenue, r.deductions, r.tax))
    annual = ryczalt(revenue(invoices, year), deductions_paid(payments, year, None), rate)
    advances = sum((p.amount for p in payments if p.type == "ryczalt" and p.year == year), ZERO)
    return PIT28Report(
        year=year,
        seller_name=seller.name,
        seller_nip=seller.nip,
        ryczalt_rate=rate,
        monthly=monthly,
        annual_sales_net=annual.revenue,
        annual_deductions=annual.deductions,
        annual_base=annual.base,
        annual_ryczalt=annual.tax,
        advances_paid=advances,
        to_pay=annual.tax - advances,
        deadline=annual_deadlines(year)["pit28"],
    )
