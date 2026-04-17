"""Testy modeli faktur — sumy Decimal, mieszane stawki VAT."""

from datetime import date
from decimal import Decimal

from jdg_ksiegowy.invoice.models import Buyer, Invoice, LineItem


def _buyer() -> Buyer:
    # NIP 5260250274 (ZUS, publiczny — poprawna suma kontrolna)
    return Buyer(name="Acme", nip="5260250274", address="ul. Krotka 1, 00-001 Warszawa")


def test_total_net_returns_decimal_for_empty_items():
    inv = Invoice(
        number="A1/04/2026",
        issue_date=date(2026, 4, 1),
        sale_date=date(2026, 4, 1),
        payment_due=date(2026, 4, 15),
        buyer=_buyer(),
        items=[],
    )
    assert inv.total_net == Decimal("0")
    assert isinstance(inv.total_net, Decimal)


def test_totals_by_vat_rate_groups_correctly():
    inv = Invoice(
        number="A2/04/2026",
        issue_date=date(2026, 4, 1),
        sale_date=date(2026, 4, 1),
        payment_due=date(2026, 4, 15),
        buyer=_buyer(),
        items=[
            LineItem(description="usluga 23", unit_price_net=Decimal("1000"), vat_rate=Decimal("23")),
            LineItem(description="usluga 23 #2", unit_price_net=Decimal("500"), vat_rate=Decimal("23")),
            LineItem(description="ksiazka", unit_price_net=Decimal("100"), vat_rate=Decimal("5")),
        ],
    )
    buckets = inv.totals_by_vat_rate()
    assert buckets[Decimal("23")] == (Decimal("1500"), Decimal("345.00"))
    assert buckets[Decimal("5")] == (Decimal("100"), Decimal("5.00"))


def test_total_vat_sums_mixed_rates():
    inv = Invoice(
        number="A3/04/2026",
        issue_date=date(2026, 4, 1),
        sale_date=date(2026, 4, 1),
        payment_due=date(2026, 4, 15),
        buyer=_buyer(),
        items=[
            LineItem(description="x", unit_price_net=Decimal("1000"), vat_rate=Decimal("23")),
            LineItem(description="y", unit_price_net=Decimal("100"), vat_rate=Decimal("8")),
        ],
    )
    assert inv.total_net == Decimal("1100")
    assert inv.total_vat == Decimal("238.00")  # 230 + 8
