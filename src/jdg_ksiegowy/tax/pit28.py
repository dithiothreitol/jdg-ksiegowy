"""Raport PIT-28 roczny dla ryczałtu — agregacja przychodów z SQLite.

PIT-28 składany do 30 kwietnia za rok poprzedni. Stawki ryczałtu:
  12% — usługi IT/programowanie (art. 12 ust. 1 pkt 2b lit. b)
  12% — inne wolne zawody
   8.5% — usługi pozostałe (w tym najem prywatny do 100 tys. PLN/rok)

Źródło: Ustawa o zryczałtowanym podatku dochodowym z 20.11.1998
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from jdg_ksiegowy.config import settings
from jdg_ksiegowy.registry.db import InvoiceRecord, get_invoices, init_db


@dataclass(frozen=True)
class MonthlyBreakdown:
    month: int
    year: int
    sales_net: Decimal
    ryczalt: Decimal


@dataclass
class PIT28Report:
    year: int
    seller_name: str
    seller_nip: str
    ryczalt_rate: Decimal
    monthly: list[MonthlyBreakdown] = field(default_factory=list)

    @property
    def annual_sales_net(self) -> Decimal:
        return sum((m.sales_net for m in self.monthly), Decimal("0"))

    @property
    def annual_ryczalt(self) -> Decimal:
        return sum((m.ryczalt for m in self.monthly), Decimal("0"))

    @property
    def annual_ryczalt_rounded(self) -> Decimal:
        return self.annual_ryczalt.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _month_sales(invoices: list[InvoiceRecord], year: int, month: int) -> Decimal:
    filtered = [i for i in invoices if i.issue_date.year == year and i.issue_date.month == month]
    return sum((Decimal(str(i.total_net)) for i in filtered), Decimal("0"))


def generate_pit28_report(year: int) -> PIT28Report:
    """Wygeneruj raport PIT-28 za wskazany rok z danych SQLite."""
    init_db()
    invoices = get_invoices()
    seller = settings.seller
    rate = seller.ryczalt_rate / 100

    monthly = []
    for month in range(1, 13):
        sales = _month_sales(invoices, year, month)
        ryczalt = (sales * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        monthly.append(MonthlyBreakdown(month=month, year=year, sales_net=sales, ryczalt=ryczalt))

    return PIT28Report(
        year=year,
        seller_name=seller.name,
        seller_nip=seller.nip,
        ryczalt_rate=seller.ryczalt_rate,
        monthly=monthly,
    )


_MONTHS_PL = [
    "",
    "Styczeń",
    "Luty",
    "Marzec",
    "Kwiecień",
    "Maj",
    "Czerwiec",
    "Lipiec",
    "Sierpień",
    "Wrzesień",
    "Październik",
    "Listopad",
    "Grudzień",
]


def format_pit28_text(report: PIT28Report) -> str:
    """Sformatuj raport PIT-28 jako czytelny tekst."""
    lines = [
        f"=== RAPORT PIT-28 za {report.year} ===",
        f"Podatnik: {report.seller_name} (NIP: {report.seller_nip})",
        f"Stawka ryczałtu: {report.ryczalt_rate}%",
        "",
        f"{'Miesiąc':<12} {'Przychód netto':>16} {'Ryczałt':>12}",
        "-" * 44,
    ]
    for m in report.monthly:
        if m.sales_net > 0:
            lines.append(f"{_MONTHS_PL[m.month]:<12} {m.sales_net:>16.2f} {m.ryczalt:>12.2f}")
    lines += [
        "-" * 44,
        f"{'RAZEM':<12} {report.annual_sales_net:>16.2f} {report.annual_ryczalt:>12.2f}",
        "",
        f"Ryczałt do zapłaty (zaokrąglony): {report.annual_ryczalt_rounded:.0f} PLN",
        "",
        "UWAGA: Kwoty pomocnicze. Przed złożeniem PIT-28 zweryfikuj",
        "z rzeczywistymi wpłatami zaliczek miesięcznych.",
    ]
    return "\n".join(lines)
