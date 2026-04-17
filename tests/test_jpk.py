"""Testy generatora JPK_V7M — mapowanie stawek, numeracja, struktura."""

from datetime import date
from decimal import Decimal

import pytest
from lxml import etree

from jdg_ksiegowy.invoice.models import Buyer, Invoice, LineItem
from jdg_ksiegowy.tax.jpk import TNS, generate_jpk_v7m


def _make_invoice(number: str, items: list[LineItem]) -> Invoice:
    return Invoice(
        number=number,
        issue_date=date(2026, 4, 1),
        sale_date=date(2026, 4, 1),
        payment_due=date(2026, 4, 15),
        buyer=Buyer(name="Acme", nip="1234567890", address="ul. X 1, 00-001 Warszawa"),
        items=items,
    )


def _ns(tag: str) -> str:
    return f"{{{TNS}}}{tag}"


def test_jpk_uses_correct_k_fields_for_8_percent():
    inv = _make_invoice("B1/04/2026", [
        LineItem(description="ksiazka", unit_price_net=Decimal("100"), vat_rate=Decimal("8")),
    ])
    xml = generate_jpk_v7m([inv], month=4, year=2026)
    root = etree.fromstring(xml.encode("utf-8"))
    wiersz = root.find(f".//{_ns('SprzedazWiersz')}")
    assert wiersz is not None
    # Stawka 8% -> K_17 (podstawa) / K_18 (VAT), NIE K_19/K_20
    assert wiersz.find(_ns("K_17")) is not None
    assert wiersz.find(_ns("K_18")) is not None
    assert wiersz.find(_ns("K_19")) is None
    assert wiersz.find(_ns("K_20")) is None


def test_jpk_lp_uses_enumerate_not_index():
    """Dwie identyczne pydantic-faktury maja inne LpSprzedazy."""
    items = [LineItem(description="x", unit_price_net=Decimal("100"), vat_rate=Decimal("23"))]
    inv1 = _make_invoice("C1/04/2026", items)
    inv2 = _make_invoice("C1/04/2026", items)  # ten sam numer + zawartosc -> rowne pydantic-modele
    xml = generate_jpk_v7m([inv1, inv2], month=4, year=2026)
    root = etree.fromstring(xml.encode("utf-8"))
    lps = [el.text for el in root.findall(f".//{_ns('LpSprzedazy')}")]
    assert lps == ["1", "2"]


def test_jpk_rejects_unsupported_vat_rate():
    inv = _make_invoice("D1/04/2026", [
        LineItem(description="x", unit_price_net=Decimal("100"), vat_rate=Decimal("13")),
    ])
    with pytest.raises(ValueError, match="nieobslugiwana stawka VAT"):
        generate_jpk_v7m([inv], month=4, year=2026)


def test_jpk_mixed_rates_within_single_invoice():
    inv = _make_invoice("E1/04/2026", [
        LineItem(description="usluga 23", unit_price_net=Decimal("1000"), vat_rate=Decimal("23")),
        LineItem(description="ksiazka 5", unit_price_net=Decimal("100"), vat_rate=Decimal("5")),
    ])
    xml = generate_jpk_v7m([inv], month=4, year=2026)
    root = etree.fromstring(xml.encode("utf-8"))
    wiersz = root.find(f".//{_ns('SprzedazWiersz')}")
    assert wiersz.find(_ns("K_19")).text == "1000.00"
    assert wiersz.find(_ns("K_20")).text == "230.00"
    assert wiersz.find(_ns("K_15")).text == "100.00"
    assert wiersz.find(_ns("K_16")).text == "5.00"
