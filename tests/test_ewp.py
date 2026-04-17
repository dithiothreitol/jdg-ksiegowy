"""Testy generatora JPK_EWP (ewidencja ryczaltowca, roczna)."""

from datetime import date
from decimal import Decimal

import pytest
from lxml import etree

from jdg_ksiegowy.invoice.models import Buyer, Invoice, LineItem
from jdg_ksiegowy.tax.ewp import TNS, generate_jpk_ewp


def _ns(t: str) -> str:
    return f"{{{TNS}}}{t}"


def _invoice(month: int, net: Decimal, num: str = "X") -> Invoice:
    return Invoice(
        number=f"{num}/{month:02d}/2026",
        issue_date=date(2026, month, 15),
        sale_date=date(2026, month, 15),
        payment_due=date(2026, month, 28),
        buyer=Buyer(name="K", nip="1111111111", address="ul. X 1"),
        items=[LineItem(description="usl", unit_price_net=net, vat_rate=Decimal("23"))],
    )


def test_ewp_aggregates_all_year():
    invoices = [_invoice(m, Decimal("1000"), str(m)) for m in range(1, 13)]
    xml = generate_jpk_ewp(invoices, year=2026, ryczalt_rate=Decimal("12"))
    root = etree.fromstring(xml.encode("utf-8"))
    wiersze = root.findall(f".//{_ns('EWPWiersz')}")
    assert len(wiersze) == 12
    ctrl = root.find(f".//{_ns('EWPCtrl')}")
    assert ctrl.find(_ns("LiczbaWierszyEWP")).text == "12"
    assert ctrl.find(_ns("SumaPrzychodow")).text == "12000.00"


def test_ewp_rejects_unknown_rate():
    inv = _invoice(4, Decimal("1000"))
    with pytest.raises(ValueError, match="nie jest w slowniku"):
        generate_jpk_ewp([inv], year=2026, ryczalt_rate=Decimal("13"))


def test_ewp_sorts_invoices_by_issue_date():
    invs = [_invoice(6, Decimal("100"), "B"), _invoice(2, Decimal("200"), "A")]
    xml = generate_jpk_ewp(invs, year=2026, ryczalt_rate=Decimal("12"))
    root = etree.fromstring(xml.encode("utf-8"))
    daty = [el.text for el in root.findall(f".//{_ns('DataWpisu')}")]
    assert daty == ["2026-02-15", "2026-06-15"]


def test_ewp_naglowek_period():
    inv = _invoice(4, Decimal("1000"))
    xml = generate_jpk_ewp([inv], year=2026, ryczalt_rate=Decimal("12"))
    root = etree.fromstring(xml.encode("utf-8"))
    nagl = root.find(f".//{_ns('Naglowek')}")
    assert nagl.find(_ns("DataOd")).text == "2026-01-01"
    assert nagl.find(_ns("DataDo")).text == "2026-12-31"
