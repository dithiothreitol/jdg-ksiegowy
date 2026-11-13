"""E2E: wygenerowane JPK_V7M(3) i JPK_EWP(4) przechodza walidacje XSD MF.

Schematy MF sa wbudowane w pakiet — testy dzialaja offline.
"""

from datetime import date
from decimal import Decimal

import pytest

from jdg_ksiegowy.expenses.models import Expense
from jdg_ksiegowy.invoice.models import Buyer, Invoice, LineItem
from jdg_ksiegowy.tax.ewp import generate_jpk_ewp
from jdg_ksiegowy.tax.jpk import generate_jpk_v7m
from jdg_ksiegowy.tax.validation import validate_jpk

# NIP zgodny z wzorcem XSD [1-9]((\d[1-9])|([1-9]\d))\d{7} + suma kontrolna
VALID_NIP = "5260250274"  # NIP ZUS, publiczny; suma=169, R=4


@pytest.fixture(scope="module")
def seller_with_valid_nip(monkeypatch_module):
    """Ustaw SELLER_NIP na NIP ktory przechodzi walidacje wzorca MF."""
    monkeypatch_module.setenv("SELLER_NIP", VALID_NIP)
    from jdg_ksiegowy.config import SellerConfig, settings

    settings.seller = SellerConfig()


@pytest.fixture(scope="module")
def monkeypatch_module():
    """Module-scoped monkeypatch (default pytest fixture jest function-scoped)."""
    from _pytest.monkeypatch import MonkeyPatch

    mp = MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture
def invoice() -> Invoice:
    return Invoice(
        number="A1/04/2026",
        issue_date=date(2026, 4, 15),
        sale_date=date(2026, 4, 15),
        payment_due=date(2026, 5, 1),
        buyer=Buyer(name="Klient", nip=VALID_NIP, address="ul. X 1, 00-001 Warszawa"),
        items=[LineItem(description="usl", unit_price_net=Decimal("5000"), vat_rate=Decimal("23"))],
    )


@pytest.fixture
def expense() -> Expense:
    return Expense(
        seller_name="Hetzner",
        seller_nip=VALID_NIP,
        seller_country="PL",
        document_number="R1",
        issue_date=date(2026, 4, 10),
        receive_date=date(2026, 4, 12),
        total_net=Decimal("100"),
        total_vat=Decimal("23"),
    )


def test_v7m3_with_expenses_passes_xsd(seller_with_valid_nip, invoice, expense):
    xml = generate_jpk_v7m([invoice], month=4, year=2026, expenses=[expense])
    result = validate_jpk(xml, "JPK_V7M_3")
    assert result.valid, "\n".join(result.errors[:5])


def test_v7m3_without_expenses_passes_xsd(seller_with_valid_nip, invoice):
    xml = generate_jpk_v7m([invoice], month=4, year=2026)
    result = validate_jpk(xml, "JPK_V7M_3")
    assert result.valid, "\n".join(result.errors[:5])


def test_v7m3_mixed_rates_passes_xsd(seller_with_valid_nip):
    inv = Invoice(
        number="B1/04/2026",
        issue_date=date(2026, 4, 15),
        sale_date=date(2026, 4, 15),
        payment_due=date(2026, 5, 1),
        buyer=Buyer(name="K", nip=VALID_NIP, address="ul. Z 1, 00-001 Warszawa"),
        items=[
            LineItem(description="usl 23", unit_price_net=Decimal("1000"), vat_rate=Decimal("23")),
            LineItem(description="ksiazka 5", unit_price_net=Decimal("100"), vat_rate=Decimal("5")),
        ],
    )
    xml = generate_jpk_v7m([inv], month=4, year=2026)
    result = validate_jpk(xml, "JPK_V7M_3")
    assert result.valid, "\n".join(result.errors[:5])


def test_v7m3_reverse_charge_passes_xsd(seller_with_valid_nip, invoice):
    """Import usług (dostawca spoza UE, bez NIP) — należny K_27/K_28 + naliczony K_42/K_43."""
    rc = Expense(
        seller_name="Anthropic PBC",
        seller_nip="",
        seller_country="US",
        document_number="21F62CC2-0034",
        issue_date=date(2026, 4, 10),
        receive_date=date(2026, 4, 10),
        total_net=Decimal("765.92"),
        total_vat=Decimal("176.16"),
        reverse_charge=True,
    )
    xml = generate_jpk_v7m([invoice], month=4, year=2026, expenses=[rc])
    result = validate_jpk(xml, "JPK_V7M_3")
    assert result.valid, "\n".join(result.errors[:5])


def test_ewp4_passes_xsd(seller_with_valid_nip, invoice):
    xml = generate_jpk_ewp([invoice], year=2026, ryczalt_rate=Decimal("12"))
    result = validate_jpk(xml, "JPK_EWP_4")
    assert result.valid, "\n".join(result.errors[:5])


def test_v7m3_correction_with_ordzu_passes_xsd(seller_with_valid_nip, invoice, expense):
    xml = generate_jpk_v7m(
        [invoice],
        month=4,
        year=2026,
        correction=1,
        expenses=[expense],
        correction_reason="Korekta po omyłkowej deklaracji zerowej pełnomocnika.",
    )
    result = validate_jpk(xml, "JPK_V7M_3")
    assert result.valid, "\n".join(result.errors[:5])


KSEF_SALE = "5260250274-20261015-0A1B2C-3D4E5F-6A"
KSEF_PURCHASE = "5260250274-20261012-ABCDEF-123456-0F"


def test_v7m3_ksef_numbers_on_sale_and_purchase_rows(seller_with_valid_nip, invoice, expense):
    """Faktury z numerem KSeF dostaja NrKSeF (nie BFK) — sprzedaz i zakup."""
    sale = invoice.model_copy(update={"ksef_number": KSEF_SALE})
    purchase = expense.model_copy(update={"ksef_number": KSEF_PURCHASE})
    xml = generate_jpk_v7m([sale], month=4, year=2026, expenses=[purchase])

    result = validate_jpk(xml)
    assert result.valid, result.errors[:5]
    assert f"<tns:NrKSeF>{KSEF_SALE}</tns:NrKSeF>" in xml
    assert f"<tns:NrKSeF>{KSEF_PURCHASE}</tns:NrKSeF>" in xml
    assert "<tns:BFK>" not in xml


def test_ewp4_ksef_number_in_k5(seller_with_valid_nip, invoice):
    xml = generate_jpk_ewp(
        [invoice.model_copy(update={"ksef_number": KSEF_SALE})],
        year=2026,
        ryczalt_rate=Decimal("12"),
    )
    assert validate_jpk(xml).valid
    assert f"<tns:K_5>{KSEF_SALE}</tns:K_5>" in xml


def test_schema_detected_from_header(seller_with_valid_nip, invoice):
    assert validate_jpk(generate_jpk_v7m([invoice], month=4, year=2026)).valid


def test_invalid_xml_is_reported(seller_with_valid_nip, invoice):
    xml = generate_jpk_v7m([invoice], month=4, year=2026).replace("<tns:P_51>", "<tns:P_99>")
    xml = xml.replace("</tns:P_51>", "</tns:P_99>")
    result = validate_jpk(xml)
    assert not result.valid and result.errors
