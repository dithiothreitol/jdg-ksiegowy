"""Regresje: JPK_EWP i PIT-28 musza ksiegowac te sama fakture w tym samym roku.

Bug: ewidencja (K_3 + wybor roku) szla po sale_date, a PIT-28 po income_date
= min(sale_date, issue_date) — faktura na przelomie roku trafiala do dwoch lat.
"""

from datetime import date
from decimal import Decimal

from lxml import etree

from jdg_ksiegowy.invoice.models import Buyer, Invoice, LineItem
from jdg_ksiegowy.tax.ewp import generate_jpk_ewp
from jdg_ksiegowy.tax.income import income_date


def _invoice(number: str, issue: date, sale: date, net: str) -> Invoice:
    return Invoice(
        id=number,
        number=number,
        issue_date=issue,
        sale_date=sale,
        payment_due=sale,
        buyer=Buyer(name="Klient", nip="1111111111", address="ul. Testowa 1"),
        items=[LineItem(description="usluga", unit_price_net=Decimal(net), vat_rate=Decimal("23"))],
    )


def test_ewp_k3_uses_income_date_not_sale_date():
    """Usluga wykonana w styczniu, faktura wystawiona w grudniu -> przychod grudniowy."""
    inv = _invoice("A9/12/2026", issue=date(2026, 12, 30), sale=date(2027, 1, 5), net="20000")
    assert income_date(inv) == date(2026, 12, 30)

    xml = generate_jpk_ewp([inv], 2026)
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.findtext(".//{*}K_2") == "2026-12-30"  # data wystawienia
    assert root.findtext(".//{*}K_3") == "2026-12-30"  # data uzyskania przychodu
    assert root.findtext(".//{*}SumaPrzychodow") == "20000.00"


def test_ewp_rows_sorted_by_income_date():
    early = _invoice("B/2", issue=date(2026, 3, 1), sale=date(2026, 2, 28), net="100")
    late = _invoice("B/1", issue=date(2026, 5, 1), sale=date(2026, 4, 30), net="200")
    xml = generate_jpk_ewp([late, early], 2026)
    root = etree.fromstring(xml.encode("utf-8"))
    numbers = [e.text for e in root.iter("{*}K_4")] or [e.text for e in root.findall(".//{*}K_4")]
    assert numbers == ["B/2", "B/1"]  # wg daty przychodu, nie kolejnosci wejscia


def test_pit28_and_ewp_agree_on_year(isolated_db):
    """Ta sama faktura: PIT-28 i JPK_EWP musza wskazac ten sam rok."""
    from jdg_ksiegowy.registry.db import InvoiceRecord, get_invoices, init_db, save_invoice
    from jdg_ksiegowy.tax.pit28 import generate_pit28_report

    init_db()
    save_invoice(
        InvoiceRecord(
            id="i-turn",
            number="A9/12/2026",
            issue_date=date(2026, 12, 30),
            sale_date=date(2027, 1, 5),
            payment_due=date(2027, 1, 19),
            buyer_name="Klient",
            buyer_nip="1234567890",
            total_net=Decimal("20000"),
            total_vat=Decimal("4600"),
            total_gross=Decimal("24600"),
            vat_rate=Decimal("23"),
        )
    )

    report = generate_pit28_report(2026)
    assert report.annual_sales_net == Decimal("20000")

    # Ewidencja skladana razem z PIT-28 musi objac te sama fakture.
    ewp_2026 = [inv for inv in get_invoices() if income_date(inv).year == 2026]
    assert [i.number for i in ewp_2026] == ["A9/12/2026"]
