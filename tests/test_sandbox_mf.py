"""E2E na bramce TESTOWEJ MF (test-e-dokumenty.mf.gov.pl). Uruchamiane jawnie: `pytest -m sandbox`.

Dane autoryzujace sa fikcyjne (poprawne sumy kontrolne) — do srodowiska testowego nie wysylamy
prawdziwych danych podatnika.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from jdg_ksiegowy.app import jpk
from jdg_ksiegowy.app.errors import ConfirmationRequiredError
from tests.helpers import InvoiceRow, save_invoice
from tests.test_sandbox_ksef import _fake_nip

pytestmark = pytest.mark.sandbox


@pytest.fixture
def sandbox_taxpayer(monkeypatch, isolated_db, tmp_path):
    from jdg_ksiegowy.config import settings

    monkeypatch.setattr(jpk, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings.mf, "env", "test")
    monkeypatch.setattr(settings.mf, "cert_path", None)
    monkeypatch.setattr(settings.mf, "cert_url", None)
    monkeypatch.setattr(settings.mf, "pesel", "44051401458")
    monkeypatch.setattr(settings.mf, "prior_income", Decimal("0"))
    monkeypatch.setattr(settings.seller, "nip", _fake_nip())


def test_submit_jpk_v7m_to_test_gateway(sandbox_taxpayer):
    save_invoice(
        InvoiceRow(number="SBX/1", issue_date=date(2026, 10, 15), total_net=Decimal("100"))
    )
    built = jpk.build_v7m(2026, 10)
    assert built.xsd_valid, built.xsd_errors

    path = Path(built.file_path)
    with pytest.raises(ConfirmationRequiredError) as pending:
        jpk.submit(path)
    filing = jpk.submit(path, confirm=pending.value.token, wait_seconds=120)

    assert filing.reference_number, filing
    # Bramka przyjela plik do przetwarzania; ostateczny wynik zalezy od weryfikacji danych
    # autoryzujacych po stronie MF (fikcyjne dane moga zostac odrzucone kodem 4xx).
    assert filing.status in {"accepted", "submitted", "rejected"}, filing
    print(f"MF test: status={filing.status} code={filing.status_code} error={filing.error}")
