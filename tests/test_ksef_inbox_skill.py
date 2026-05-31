"""Testy skilla inbox.py — preview/save, dedup, flagi manual, not-configured.

KSeFClient.query_inbox/download_invoice_xml/is_configured sa mockowane — zero sieci.
"""

import importlib.util
import json
import sys
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INBOX_PATH = REPO_ROOT / "skills" / "ksef" / "scripts" / "inbox.py"

_spec = importlib.util.spec_from_file_location("ksef_inbox", INBOX_PATH)
inbox = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(inbox)


def _meta(**over):
    base = dict(
        ksef_number="5261040567-20260525-AAAAAA-01",
        invoice_number="FV/2026/05/123",
        issue_date=date(2026, 5, 25),
        invoicing_date=datetime(2026, 5, 25, 16, 5),
        acquisition_date=datetime(2026, 5, 26, 8, 0),
        seller=SimpleNamespace(nip="5261040567", name="Shell Polska sp. z o.o."),
        buyer=SimpleNamespace(identifier="7591323387", name="ArchXS"),
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


def _patch_client(monkeypatch, *, metadata, downloads=None, configured=True):
    """Podstaw metody KSeFClient. `downloads` to lista, do ktorej trafiaja ksef_number."""
    monkeypatch.setattr(inbox.KSeFClient, "is_configured", lambda self: configured)
    monkeypatch.setattr(
        inbox.KSeFClient,
        "query_inbox",
        lambda self, date_from, date_to, role="buyer", include_corrections=False, seller_nip=None: (
            list(metadata)
        ),
    )

    def _download(self, ksef_number):
        if downloads is not None:
            downloads.append(ksef_number)
        return b"<Faktura/>"

    monkeypatch.setattr(inbox.KSeFClient, "download_invoice_xml", _download)


def _run(monkeypatch, capsys, argv):
    monkeypatch.setattr(sys, "argv", ["inbox.py", *argv])
    inbox.main()
    return json.loads(capsys.readouterr().out)


def test_preview_lists_new_without_saving(isolated_db, monkeypatch, capsys):
    from jdg_ksiegowy.registry.db import get_expenses

    _patch_client(monkeypatch, metadata=[_meta()])
    out = _run(monkeypatch, capsys, ["--month", "5", "--year", "2026"])

    assert out["success"] is True
    assert out["saved"] is False
    assert out["count"] == 1
    assert out["invoices"][0]["status"] == "new"
    assert out["invoices"][0]["category"] == "paliwo"
    assert get_expenses() == []  # preview nic nie zapisuje


def test_save_persists_with_ksef_number_and_xml(isolated_db, monkeypatch, capsys, tmp_path):
    from jdg_ksiegowy.registry.db import get_expenses

    monkeypatch.setattr(inbox, "XML_DIR", tmp_path / "xml")
    _patch_client(monkeypatch, metadata=[_meta()])

    out = _run(monkeypatch, capsys, ["--month", "5", "--year", "2026", "--save"])

    assert out["saved"] is True
    assert out["saved_count"] == 1
    inv = out["invoices"][0]
    assert inv["status"] == "saved"
    assert inv["file_path"] is not None
    assert Path(inv["file_path"]).exists()

    records = get_expenses()
    assert len(records) == 1
    assert records[0].ksef_number == "5261040567-20260525-AAAAAA-01"


def test_save_is_idempotent(isolated_db, monkeypatch, capsys, tmp_path):
    from jdg_ksiegowy.registry.db import get_expenses

    monkeypatch.setattr(inbox, "XML_DIR", tmp_path / "xml")
    _patch_client(monkeypatch, metadata=[_meta()])

    _run(monkeypatch, capsys, ["--month", "5", "--year", "2026", "--save"])
    out2 = _run(monkeypatch, capsys, ["--month", "5", "--year", "2026", "--save"])

    assert out2["saved_count"] == 0
    assert out2["invoices"][0]["status"] == "exists"
    assert len(get_expenses()) == 1


def test_foreign_currency_marked_manual_and_not_saved(isolated_db, monkeypatch, capsys, tmp_path):
    from jdg_ksiegowy.registry.db import get_expenses

    monkeypatch.setattr(inbox, "XML_DIR", tmp_path / "xml")
    downloads: list[str] = []
    _patch_client(monkeypatch, metadata=[_meta(currency="EUR")], downloads=downloads)

    out = _run(monkeypatch, capsys, ["--month", "5", "--year", "2026", "--save"])

    inv = out["invoices"][0]
    assert inv["status"] == "manual"
    assert "EUR" in inv["manual_reason"]
    assert out["saved_count"] == 0
    assert get_expenses() == []
    assert downloads == []  # nie pobieramy XML dla pozycji do recznej obslugi


def test_include_corrections_flag_passed_through(isolated_db, monkeypatch, capsys):
    seen = {}

    monkeypatch.setattr(inbox.KSeFClient, "is_configured", lambda self: True)

    def _query(self, date_from, date_to, role="buyer", include_corrections=False, seller_nip=None):
        seen["include_corrections"] = include_corrections
        seen["seller_nip"] = seller_nip
        return []

    monkeypatch.setattr(inbox.KSeFClient, "query_inbox", _query)

    _run(
        monkeypatch,
        capsys,
        ["--month", "5", "--year", "2026", "--include-corrections", "--seller-nip", "5261009190"],
    )
    assert seen["include_corrections"] is True
    assert seen["seller_nip"] == "5261009190"


def test_not_configured_returns_error(monkeypatch, capsys):
    from jdg_ksiegowy.config import settings

    monkeypatch.setattr(settings.ksef, "nip", "")
    monkeypatch.setattr(settings.ksef, "token", "")
    monkeypatch.setattr(settings.ksef, "env", "prod")

    monkeypatch.setattr(sys, "argv", ["inbox.py", "--month", "5", "--year", "2026"])
    with pytest.raises(SystemExit):
        inbox.main()

    out = json.loads(capsys.readouterr().out)
    assert out["success"] is False
    assert "KSEF_TOKEN" in out["error"]
