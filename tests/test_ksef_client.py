"""KSeFClient.send_invoice i backfill numerow KSeF — SDK zastapione atrapa, zero sieci."""

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from ksef2 import KSeFException, KSeFInvoiceProcessingTimeoutError, KSeFInvoiceRejectedError

from jdg_ksiegowy.ksef.backfill import backfill_ksef_numbers
from jdg_ksiegowy.ksef.client import KSeFClient
from jdg_ksiegowy.registry.repository import InvoiceRepository
from tests.helpers import InvoiceRow, save_invoice

KSEF_NUMBER = "1234567890-20261013-0A1B2C-3D4E5F-6A"


class _Submission:
    def __init__(self, status, *, wait_error=None, upo_error=None):
        self._status, self._wait_error, self._upo_error = status, wait_error, upo_error
        self.reference_number = "20261013-EE-REF"

    def wait(self, timeout):
        if self._wait_error:
            raise self._wait_error
        return self._status

    def download_upo(self):
        if self._upo_error:
            raise self._upo_error
        return b"<UPO/>"


class _Session:
    def __init__(self, submission=None, error=None):
        self._submission, self._error = submission, error
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def send_invoice(self, xml):
        self.sent.append(xml)
        if self._error:
            raise self._error
        return self._submission


def _client_with(monkeypatch, session):
    monkeypatch.setattr(
        KSeFClient,
        "_authenticated_client",
        lambda self: SimpleNamespace(online_session=lambda form_code: session),
    )
    return KSeFClient()


def test_send_returns_ksef_number_acquisition_date_and_upo(monkeypatch):
    acquired = datetime(2026, 10, 13, 9, 15)
    status = SimpleNamespace(
        ksef_number=KSEF_NUMBER, reference_number="20261013-EE-REF", acquisition_date=acquired
    )
    session = _Session(_Submission(status))
    result = _client_with(monkeypatch, session).send_invoice("<Faktura/>")

    assert result.success is True
    assert result.ksef_number == KSEF_NUMBER
    assert result.reference_number == "20261013-EE-REF"
    assert result.acquired_at == acquired
    assert result.upo == b"<UPO/>"
    assert session.sent == [b"<Faktura/>"]


def _rejected() -> KSeFInvoiceRejectedError:
    status = SimpleNamespace(
        status=SimpleNamespace(code=450, description="Blad semantyki", details=[], extensions=None),
        ksef_number=None,
    )
    return KSeFInvoiceRejectedError(invoice_reference_number="20261013-EE-REF", status=status)


def test_processing_timeout_keeps_reference_for_duplicate_guard(monkeypatch):
    timeout = KSeFInvoiceProcessingTimeoutError(
        invoice_reference_number="20261013-EE-REF", timeout=120
    )
    session = _Session(_Submission(None, wait_error=timeout))
    result = _client_with(monkeypatch, session).send_invoice("<Faktura/>")
    assert (result.success, result.rejected, result.ksef_number) == (False, False, None)
    assert result.reference_number == "20261013-EE-REF"


def test_rejection_is_marked_so_invoice_can_be_fixed_and_resent(monkeypatch):
    session = _Session(_Submission(None, wait_error=_rejected()))
    result = _client_with(monkeypatch, session).send_invoice("<Faktura/>")
    assert result.rejected is True and "450" in (result.error or "")


def test_missing_upo_does_not_lose_assigned_ksef_number(monkeypatch):
    status = SimpleNamespace(
        ksef_number=KSEF_NUMBER, reference_number="20261013-EE-REF", acquisition_date=None
    )
    session = _Session(_Submission(status, upo_error=KSeFException("UPO not ready")))
    result = _client_with(monkeypatch, session).send_invoice("<Faktura/>")
    assert result.success is True and result.ksef_number == KSEF_NUMBER and result.upo is None


def test_send_rejection_is_reported_not_raised(monkeypatch):
    session = _Session(error=KSeFException("Faktura odrzucona: 450"))
    result = _client_with(monkeypatch, session).send_invoice("<Faktura/>")

    assert result.success is False
    assert "450" in result.error
    assert result.ksef_number is None


def test_backfill_matches_by_invoice_number(isolated_db):
    save_invoice(
        InvoiceRow(
            number="A1/10/2026",
            issue_date=date(2026, 10, 1),
            total_net=Decimal("100"),
            ksef_reference="20261001-EE-REF",
        )
    )
    save_invoice(
        InvoiceRow(number="A2/10/2026", issue_date=date(2026, 10, 2), total_net=Decimal("100"))
    )
    acquired = datetime(2026, 10, 1, 12, 0)
    calls = []

    class FakeClient:
        def query_metadata(self, date_from, date_to, *, role, include_corrections):
            calls.append((date_from, date_to, role))
            return [
                SimpleNamespace(
                    invoice_number="A1/10/2026", ksef_number=KSEF_NUMBER, acquisition_date=acquired
                )
            ]

    repo = InvoiceRepository()
    preview = backfill_ksef_numbers(FakeClient(), repo, today=date(2026, 11, 13), apply=False)
    assert [m.invoice_number for m in preview.matched] == ["A1/10/2026"]
    assert preview.missing == ["A2/10/2026"]
    assert repo.get("A1/10/2026").ksef_number is None  # podglad nic nie zapisuje
    assert calls == [(date(2026, 10, 1), date(2026, 11, 13), "seller")]

    backfill_ksef_numbers(FakeClient(), repo, today=date(2026, 11, 13), apply=True)
    inv = repo.get("A1/10/2026")
    assert inv.ksef_number == KSEF_NUMBER and inv.ksef_acquired_at == acquired


def test_backfill_rejects_malformed_number(isolated_db):
    save_invoice(
        InvoiceRow(number="A1/10/2026", issue_date=date(2026, 10, 1), total_net=Decimal("100"))
    )

    class FakeClient:
        def query_metadata(self, *a, **k):
            return [
                SimpleNamespace(
                    invoice_number="A1/10/2026", ksef_number="ZLY", acquisition_date=None
                )
            ]

    with pytest.raises(ValueError, match="numer KSeF"):
        backfill_ksef_numbers(
            FakeClient(), InvoiceRepository(), today=date(2026, 11, 13), apply=True
        )
