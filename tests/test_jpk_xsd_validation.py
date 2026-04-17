"""E2E: wygenerowane JPK_V7M(3) i JPK_EWP(4) przechodza walidacje XSD MF.

Test pobiera oficjalne XSD z podatki.gov.pl przy pierwszym uruchomieniu
(potem cache'uje w `data/xsd/`). Wymaga internetu tylko raz.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from jdg_ksiegowy.expenses.models import Expense
from jdg_ksiegowy.invoice.models import Buyer, Invoice, LineItem
from jdg_ksiegowy.tax.ewp import generate_jpk_ewp
from jdg_ksiegowy.tax.jpk import generate_jpk_v7m
from jdg_ksiegowy.tax.validation import JPKValidator


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


@pytest.fixture(scope="module")
def validator(tmp_path_factory) -> JPKValidator:
    cache = tmp_path_factory.mktemp("xsd_cache")
    return JPKValidator(cache_dir=cache)


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


@pytest.mark.xsd
def test_v7m3_with_expenses_passes_xsd(seller_with_valid_nip, validator, invoice, expense):
    xml = generate_jpk_v7m([invoice], month=4, year=2026, expenses=[expense])
    result = validator.validate(xml, schema="JPK_V7M_3")
    assert result.valid, "\n".join(result.errors[:5])


@pytest.mark.xsd
def test_v7m3_without_expenses_passes_xsd(seller_with_valid_nip, validator, invoice):
    xml = generate_jpk_v7m([invoice], month=4, year=2026)
    result = validator.validate(xml, schema="JPK_V7M_3")
    assert result.valid, "\n".join(result.errors[:5])


@pytest.mark.xsd
def test_v7m3_mixed_rates_passes_xsd(seller_with_valid_nip, validator):
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
    result = validator.validate(xml, schema="JPK_V7M_3")
    assert result.valid, "\n".join(result.errors[:5])


@pytest.mark.xsd
def test_ewp4_passes_xsd(seller_with_valid_nip, validator, invoice):
    xml = generate_jpk_ewp([invoice], year=2026, ryczalt_rate=Decimal("12"))
    result = validator.validate(xml, schema="JPK_EWP_4")
    assert result.valid, "\n".join(result.errors[:5])
