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
    inv = _make_invoice(
        "B1/04/2026",
        [
            LineItem(description="ksiazka", unit_price_net=Decimal("100"), vat_rate=Decimal("8")),
        ],
    )
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
    inv = _make_invoice(
        "V3/04/2026",
        [
            LineItem(description="x", unit_price_net=Decimal("100"), vat_rate=Decimal("23")),
        ],
    )
    xml = generate_jpk_v7m([inv], month=4, year=2026)
    root = etree.fromstring(xml.encode("utf-8"))
    assert TNS == "http://crd.gov.pl/wzor/2025/12/19/14090/"
    kod = root.find(f".//{_ns('KodFormularza')}")
    assert kod.get("kodSystemowy") == "JPK_V7M (3)"
    assert root.find(f".//{_ns('WariantFormularza')}").text == "3"
    assert root.find(f".//{_ns('WariantFormularzaDekl')}").text == "23"


def test_jpk_v7m_sprzedaz_wiersz_uses_bfk_by_default():
    """Faktura bez numeru KSeF -> BFK=1 (faktura poza KSeF)."""
    inv = _make_invoice(
        "B/04/2026",
        [
            LineItem(description="x", unit_price_net=Decimal("100"), vat_rate=Decimal("23")),
        ],
    )
    xml = generate_jpk_v7m([inv], month=4, year=2026)
    root = etree.fromstring(xml.encode("utf-8"))
    wiersz = root.find(f".//{_ns('SprzedazWiersz')}")
    assert wiersz.find(_ns("BFK")).text == "1"
    assert wiersz.find(_ns("NrKSeF")) is None
    assert wiersz.find(_ns("OFF")) is None
    assert wiersz.find(_ns("DI")) is None


def test_jpk_v7m_sprzedaz_wiersz_uses_nrksef_when_present():
    inv = _make_invoice(
        "K/04/2026",
        [
            LineItem(description="x", unit_price_net=Decimal("100"), vat_rate=Decimal("23")),
        ],
    )
    inv.ksef_number = "5260250274-20260415-0A1B2C-3D4E5F-6A"
    xml = generate_jpk_v7m([inv], month=4, year=2026)
    root = etree.fromstring(xml.encode("utf-8"))
    wiersz = root.find(f".//{_ns('SprzedazWiersz')}")
    assert wiersz.find(_ns("NrKSeF")).text == "5260250274-20260415-0A1B2C-3D4E5F-6A"
    assert wiersz.find(_ns("BFK")) is None


def test_session_reference_alone_is_not_a_ksef_number():
    """Regresja: numer referencyjny wysylki nie moze trafic do NrKSeF (blad z wersji 0.2)."""
    inv = _make_invoice(
        "C/04/2026",
        [LineItem(description="x", unit_price_net=Decimal("100"), vat_rate=Decimal("23"))],
    )
    inv.ksef_reference = "20260415-EE-1A2B3C4D5E-6F"
    xml = generate_jpk_v7m([inv], month=4, year=2026)
    wiersz = etree.fromstring(xml.encode("utf-8")).find(f".//{_ns('SprzedazWiersz')}")
    assert wiersz.find(_ns("NrKSeF")) is None
    assert wiersz.find(_ns("BFK")).text == "1"


def test_invalid_ksef_number_rejected_by_model():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="numer KSeF"):
        Invoice(
            number="D/04/2026",
            issue_date=date(2026, 4, 1),
            sale_date=date(2026, 4, 1),
            payment_due=date(2026, 4, 15),
            buyer=Buyer(name="Acme", nip="5260250274", address="ul. X 1"),
            items=[],
            ksef_number="20260415-EE-1A2B3C4D5E-6F",
        )


def test_jpk_v7m_required_zero_fields_present():
    """K_10-K_14, K_21-K_22, K_33-K_36 musza byc w wierszu (0.00 jesli nieuzywane)."""
    inv = _make_invoice(
        "Z/04/2026",
        [
            LineItem(description="x", unit_price_net=Decimal("100"), vat_rate=Decimal("23")),
        ],
    )
    xml = generate_jpk_v7m([inv], month=4, year=2026)
    root = etree.fromstring(xml.encode("utf-8"))
    wiersz = root.find(f".//{_ns('SprzedazWiersz')}")
    for tag in (
        "K_10",
        "K_11",
        "K_12",
        "K_13",
        "K_14",
        "K_21",
        "K_22",
        "K_33",
        "K_34",
        "K_35",
        "K_36",
    ):
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
    inv = _make_invoice(
        "D1/04/2026",
        [
            LineItem(description="x", unit_price_net=Decimal("100"), vat_rate=Decimal("13")),
        ],
    )
    with pytest.raises(ValueError, match="nieobslugiwana stawka VAT"):
        generate_jpk_v7m([inv], month=4, year=2026)


def test_jpk_mixed_rates_within_single_invoice():
    inv = _make_invoice(
        "E1/04/2026",
        [
            LineItem(
                description="usluga 23", unit_price_net=Decimal("1000"), vat_rate=Decimal("23")
            ),
            LineItem(description="ksiazka 5", unit_price_net=Decimal("100"), vat_rate=Decimal("5")),
        ],
    )
    xml = generate_jpk_v7m([inv], month=4, year=2026)
    root = etree.fromstring(xml.encode("utf-8"))
    wiersz = root.find(f".//{_ns('SprzedazWiersz')}")
    assert wiersz.find(_ns("K_19")).text == "1000.00"
    assert wiersz.find(_ns("K_20")).text == "230.00"
    assert wiersz.find(_ns("K_15")).text == "100.00"
    assert wiersz.find(_ns("K_16")).text == "5.00"


def _single_invoice(number: str = "F/04/2026") -> Invoice:
    return _make_invoice(
        number, [LineItem(description="x", unit_price_net=Decimal("100"), vat_rate=Decimal("23"))]
    )


def test_jpk_original_has_cel_zlozenia_1_and_no_ordzu():
    xml = generate_jpk_v7m([_single_invoice()], month=4, year=2026)
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.find(f".//{_ns('CelZlozenia')}").text == "1"
    assert root.find(f".//{_ns('P_ORDZU')}") is None


@pytest.mark.parametrize("correction", [1, 2])
def test_jpk_correction_always_uses_cel_zlozenia_2(correction):
    """XSD JPK_V7M(3): CelZlozenia to enum {1, 2} — druga korekta to nadal '2', nie '3'."""
    xml = generate_jpk_v7m([_single_invoice()], month=4, year=2026, correction=correction)
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.find(f".//{_ns('CelZlozenia')}").text == "2"


def test_jpk_correction_reason_goes_to_p_ordzu_as_last_pozycja():
    reason = "Pełnomocnik omyłkowo złożył deklarację zerową."
    xml = generate_jpk_v7m(
        [_single_invoice()], month=4, year=2026, correction=1, correction_reason=reason
    )
    root = etree.fromstring(xml.encode("utf-8"))
    poz = root.find(f".//{_ns('PozycjeSzczegolowe')}")
    # XSD: P_ORDZU to ostatni element sekwencji PozycjeSzczegolowe (tuz przed Pouczenia).
    assert poz[-1].tag == _ns("P_ORDZU")
    assert poz[-1].text == reason
