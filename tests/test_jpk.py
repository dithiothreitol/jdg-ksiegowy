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
        buyer=Buyer(name="Acme", nip="5260250274", address="ul. X 1, 00-001 Warszawa"),
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
    # Stawka 8% -> K_17 (podstawa) / K_18 (VAT) wypelnione rzeczywistym
    assert wiersz.find(_ns("K_17")).text == "100.00"
    assert wiersz.find(_ns("K_18")).text == "8.00"
    # K_19/K_20 nie powinny byc dodane (opcjonalne, nieuzywane)
    assert wiersz.find(_ns("K_19")) is None
    assert wiersz.find(_ns("K_20")) is None


def test_jpk_v7m_uses_v3_tns_and_variant():
    inv = _make_invoice("V3/04/2026", [
        LineItem(description="x", unit_price_net=Decimal("100"), vat_rate=Decimal("23")),
    ])
    xml = generate_jpk_v7m([inv], month=4, year=2026)
    root = etree.fromstring(xml.encode("utf-8"))
    assert TNS == "http://crd.gov.pl/wzor/2025/06/18/06181/"
    kod = root.find(f".//{_ns('KodFormularza')}")
    assert kod.get("kodSystemowy") == "JPK_V7M (3)"
    assert root.find(f".//{_ns('WariantFormularza')}").text == "3"
    assert root.find(f".//{_ns('WariantFormularzaDekl')}").text == "23"


def test_jpk_v7m_sprzedaz_wiersz_uses_bfk_by_default():
    """Faktura bez ksef_reference -> BFK=1 (faktura poza KSeF)."""
    inv = _make_invoice("B/04/2026", [
        LineItem(description="x", unit_price_net=Decimal("100"), vat_rate=Decimal("23")),
    ])
    xml = generate_jpk_v7m([inv], month=4, year=2026)
    root = etree.fromstring(xml.encode("utf-8"))
    wiersz = root.find(f".//{_ns('SprzedazWiersz')}")
    assert wiersz.find(_ns("BFK")).text == "1"
    assert wiersz.find(_ns("NrKSeF")) is None
    assert wiersz.find(_ns("OFF")) is None
    assert wiersz.find(_ns("DI")) is None


def test_jpk_v7m_sprzedaz_wiersz_uses_nrksef_when_present():
    inv = _make_invoice("K/04/2026", [
        LineItem(description="x", unit_price_net=Decimal("100"), vat_rate=Decimal("23")),
    ])
    inv.ksef_reference = "KSEF-2026-04-15-ABC"
    xml = generate_jpk_v7m([inv], month=4, year=2026)
    root = etree.fromstring(xml.encode("utf-8"))
    wiersz = root.find(f".//{_ns('SprzedazWiersz')}")
    assert wiersz.find(_ns("NrKSeF")).text == "KSEF-2026-04-15-ABC"
    assert wiersz.find(_ns("BFK")) is None


def test_jpk_v7m_required_zero_fields_present():
    """K_10-K_14, K_21-K_22, K_33-K_36 musza byc w wierszu (0.00 jesli nieuzywane)."""
    inv = _make_invoice("Z/04/2026", [
        LineItem(description="x", unit_price_net=Decimal("100"), vat_rate=Decimal("23")),
    ])
    xml = generate_jpk_v7m([inv], month=4, year=2026)
    root = etree.fromstring(xml.encode("utf-8"))
    wiersz = root.find(f".//{_ns('SprzedazWiersz')}")
    for tag in ("K_10", "K_11", "K_12", "K_13", "K_14", "K_21", "K_22", "K_33", "K_34", "K_35", "K_36"):
        el = wiersz.find(_ns(tag))
        assert el is not None, f"Brak wymaganego pola {tag}"
        assert el.text == "0.00", f"{tag} powinno byc 0.00, jest {el.text}"


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
