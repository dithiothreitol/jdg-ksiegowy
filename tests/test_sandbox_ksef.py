"""E2E na srodowisku TESTOWYM KSeF (siec). Uruchamiane jawnie: `pytest -m sandbox`.

Sprzedawca i nabywca maja losowe, fikcyjne NIP-y: srodowisko testowe KSeF
pozwala zalogowac sie certyfikatem testowym jako dowolny NIP, wiec nie wolno
tam wysylac prawdziwych danych firmy.
"""

import random
from datetime import date
from decimal import Decimal

import pytest

from jdg_ksiegowy.invoice.generator_xml import generate_invoice_xml
from jdg_ksiegowy.invoice.models import Buyer, Invoice, LineItem
from jdg_ksiegowy.ksef.client import KSeFClient
from jdg_ksiegowy.validators import is_ksef_number, validate_nip

pytestmark = pytest.mark.sandbox


def _fake_nip() -> str:
    while True:
        head = f"{random.randint(1, 9)}{random.randint(1, 9)}{random.randint(1, 9)}" + "".join(
            str(random.randint(0, 9)) for _ in range(6)
        )
        weights = (6, 5, 7, 2, 3, 4, 5, 6, 7)
        check = sum(w * int(d) for w, d in zip(weights, head, strict=True)) % 11
        if check != 10 and validate_nip(nip := head + str(check)):
            return nip


@pytest.fixture
def sandbox_seller(monkeypatch):
    from jdg_ksiegowy.config import settings

    nip = _fake_nip()
    monkeypatch.setattr(settings.ksef, "env", "test")
    monkeypatch.setattr(settings.ksef, "token", "")
    monkeypatch.setattr(settings.ksef, "nip", nip)
    monkeypatch.setattr(settings.seller, "nip", nip)
    monkeypatch.setattr(settings.seller, "name", "Sandbox Testowy JDG")
    monkeypatch.setattr(settings.seller, "address", "ul. Testowa 1, 00-001 Warszawa")
    monkeypatch.setattr(settings.seller, "bank_account", "")
    return nip


def test_send_invoice_returns_ksef_number_and_upo(sandbox_seller):
    today = date.today()
    invoice = Invoice(
        number=f"SBX{random.randint(1000, 9999)}/{today:%m/%Y}",
        issue_date=today,
        sale_date=today,
        payment_due=today,
        buyer=Buyer(name="Nabywca Sandbox", nip=_fake_nip(), address="ul. Inna 2, 00-002 Warszawa"),
        items=[LineItem(description="Test e2e", unit_price_net=Decimal("100"))],
    )
    client = KSeFClient()
    assert client.env == "test"

    result = client.send_invoice(generate_invoice_xml(invoice))

    assert result.success, result.error
    assert result.ksef_number and is_ksef_number(result.ksef_number)
    assert result.ksef_number.startswith(sandbox_seller)
    assert result.reference_number and result.reference_number != result.ksef_number
    assert result.upo and b"<" in result.upo
