"""Warstwa aplikacyjna KSeF i JPK — przypadki przeniesione z testow skryptow 0.x."""

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from jdg_ksiegowy.app import jpk as jpk_app
from jdg_ksiegowy.app import ksef as ksef_app
from jdg_ksiegowy.app.errors import ConfigMissingError
from jdg_ksiegowy.ksef.client import KSeFClient
from jdg_ksiegowy.registry.repository import ExpenseRepository
from jdg_ksiegowy.tax.validation import schema_name

KSEF_NUMBER = "5261040567-20260525-AAAAAA-AAAAAA-01"
MAY = (date(2026, 5, 1), date(2026, 5, 31))


def _meta(**over):
    base = dict(
        ksef_number=KSEF_NUMBER,
        invoice_number="FV/2026/05/123",
        issue_date=date(2026, 5, 25),
        invoicing_date=datetime(2026, 5, 25, 16, 5),
        acquisition_date=datetime(2026, 5, 26, 8, 0),
        seller=SimpleNamespace(nip="5261040567", name="Shell Polska sp. z o.o."),
        buyer=SimpleNamespace(identifier="1234563218", name="Kupujacy"),
        net_amount=147.06,
        vat_amount=33.83,
        gross_amount=180.89,
        currency="PLN",
        invoice_type="vat",
        is_self_invoicing=False,
        has_attachment=False,
    )
    base.update(over)
    return SimpleNamespace(**base)


@pytest.fixture
def ksef_fake(monkeypatch, isolated_db, tmp_path):
    """KSeFClient bez sieci; zwraca slownik z zapamietanymi wywolaniami."""
    state: dict = {"metadata": [_meta()], "downloads": [], "query": {}}
    monkeypatch.setattr(ksef_app, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(KSeFClient, "is_configured", lambda self: True)

    def query(
        self, date_from, date_to, *, role="buyer", include_corrections=False, seller_nip=None
    ):
        state["query"] = {"role": role, "corrections": include_corrections, "nip": seller_nip}
        return list(state["metadata"])

    def download(self, ksef_number):
        state["downloads"].append(ksef_number)
        return b"<Faktura/>"

    monkeypatch.setattr(KSeFClient, "query_metadata", query)
    monkeypatch.setattr(KSeFClient, "download_invoice_xml", download)
    return state


def test_inbox_preview_lists_new_without_saving(ksef_fake):
    result = ksef_app.inbox(*MAY)
    assert [i.status for i in result.invoices] == ["new"]
    assert result.invoices[0].category == "paliwo"
    assert ExpenseRepository().list() == []


def test_inbox_save_persists_with_ksef_number_and_xml(ksef_fake):
    result = ksef_app.inbox(*MAY, save=True)
    item = result.invoices[0]
    assert (item.status, result.saved_count) == ("saved", 1)
    (expense,) = ExpenseRepository().list()
    assert expense.ksef_number == KSEF_NUMBER
    assert expense.file_path and expense.file_path.endswith(".xml")


def test_inbox_save_is_idempotent(ksef_fake):
    ksef_app.inbox(*MAY, save=True)
    again = ksef_app.inbox(*MAY, save=True)
    assert again.saved_count == 0 and again.invoices[0].status == "exists"
    assert len(ExpenseRepository().list()) == 1


def test_inbox_foreign_currency_is_manual_and_not_downloaded(ksef_fake):
    ksef_fake["metadata"] = [_meta(currency="EUR")]
    result = ksef_app.inbox(*MAY, save=True)
    assert result.invoices[0].status == "manual"
    assert "EUR" in (result.invoices[0].manual_reason or "")
    assert ksef_fake["downloads"] == [] and ExpenseRepository().list() == []


def test_inbox_passes_filters_through(ksef_fake):
    ksef_app.inbox(*MAY, include_corrections=True, seller_nip="5261009190", role="seller")
    assert ksef_fake["query"] == {"role": "seller", "corrections": True, "nip": "5261009190"}


def test_ksef_not_configured(isolated_db, monkeypatch):
    from jdg_ksiegowy.config import settings

    monkeypatch.setattr(settings.ksef, "env", "prod")
    monkeypatch.setattr(settings.ksef, "token", "")
    with pytest.raises(ConfigMissingError, match="KSeF"):
        ksef_app.inbox(*MAY)


def test_correction_numbering(tmp_path, monkeypatch):
    monkeypatch.setattr(jpk_app, "DATA_DIR", tmp_path)
    jpk_dir = tmp_path / "jpk"
    jpk_dir.mkdir()
    (jpk_dir / "JPK_V7M_2026_03.xml").touch()  # oryginal nie liczy sie jako korekta
    assert jpk_app._next_correction_path("JPK_V7M_2026_03")[0] == 1
    for name in ("JPK_V7M_2026_03_K1.xml", "JPK_V7M_2026_03_K2.xml", "JPK_V7M_2026_04_K1.xml"):
        (jpk_dir / name).touch()
    n, path = jpk_app._next_correction_path("JPK_V7M_2026_03")
    assert (n, path.name) == (3, "JPK_V7M_2026_03_K3.xml")


def test_schema_name_from_kod_systemowy():
    xml = (
        b'<JPK xmlns="urn:x"><Naglowek>'
        b'<KodFormularza kodSystemowy="JPK_V7M (3)">JPK_VAT</KodFormularza>'
        b"</Naglowek></JPK>"
    )
    assert schema_name(xml) == "JPK_V7M_3"


def test_submit_requires_pesel(isolated_db, monkeypatch):
    from jdg_ksiegowy.config import settings

    monkeypatch.setattr(settings.mf, "pesel", "")
    with pytest.raises(ConfigMissingError, match="MF_PESEL"):
        jpk_app._authorization()
