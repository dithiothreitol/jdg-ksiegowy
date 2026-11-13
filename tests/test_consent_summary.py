"""Podsumowania zgody: porownanie z poprzednim okresem i z rejestrem przed wysylka."""

import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from rich.console import Console

from jdg_ksiegowy.app import invoices as invoices_app
from jdg_ksiegowy.app import jpk as jpk_app
from jdg_ksiegowy.app import ksef as ksef_app
from jdg_ksiegowy.app.errors import ConfirmationRequiredError
from jdg_ksiegowy.cli.output import _summary_panel
from jdg_ksiegowy.registry.repository import FilingRepository
from tests.helpers import InvoiceRow, save_invoice


@pytest.fixture(autouse=True)
def _setup(isolated_db, monkeypatch, tmp_path):
    from jdg_ksiegowy.config import settings

    monkeypatch.setattr(settings.mf, "env", "test")
    monkeypatch.setattr(settings.mf, "pesel", "44051401458")
    monkeypatch.setattr(settings.ksef, "env", "test")
    monkeypatch.setattr(settings.ksef, "nip", "1234567890")
    for module in (invoices_app, jpk_app):
        monkeypatch.setattr(module, "DATA_DIR", tmp_path / "data")


def _summary(action, *args) -> dict:
    """Pierwsza faza czynnosci nieodwracalnej: podsumowanie bez wysylki."""
    with pytest.raises(ConfirmationRequiredError) as exc:
        action(*args)
    return exc.value.summary


# --- JPK_V7M ---------------------------------------------------------------------------


def _sale(number: str, day: date, net: str) -> None:
    save_invoice(InvoiceRow(number=number, issue_date=day, total_net=Decimal(net)))


def _accept(built: jpk_app.JpkBuildResult, env: str = "test") -> None:
    """Zapisz zbudowany plik jako deklaracje przyjeta przez MF."""
    repo = FilingRepository()
    filing = repo.create(
        form=built.form,
        year=built.year,
        month=built.month,
        purpose=built.purpose,
        file_path=built.file_path,
        sha256="przyjeta",
        env=env,
    )
    repo.update(filing.id, status="accepted")


def _submit_summary(built: jpk_app.JpkBuildResult) -> dict:
    assert built.xsd_valid, built.xsd_errors
    return _summary(jpk_app.submit, Path(built.file_path))


def test_first_declaration_has_nothing_to_compare():
    _sale("A1/10/2026", date(2026, 10, 20), "500")
    summary = _submit_summary(jpk_app.build_v7m(2026, 10))
    assert summary["poprzednio"] == "brak przyjętej deklaracji za 2026-09"
    assert "uwaga" not in summary


def test_declaration_is_compared_with_previous_month():
    _sale("A1/09/2026", date(2026, 9, 20), "1000")  # VAT 230
    _accept(jpk_app.build_v7m(2026, 9))
    _sale("A1/10/2026", date(2026, 10, 20), "500")  # VAT 115
    summary = _submit_summary(jpk_app.build_v7m(2026, 10))
    previous = summary["poprzednio"]
    assert previous["deklaracja"].startswith("2026-09, złożona ")
    assert previous["P_38"] == "230 (zmiana -115)"
    assert previous["P_48"] == "0 (bez zmian)"
    assert previous["P_51"] == "230 (zmiana -115)"
    assert "uwaga" not in summary


def test_previous_month_from_other_environment_is_ignored():
    _sale("A1/09/2026", date(2026, 9, 20), "1000")
    _accept(jpk_app.build_v7m(2026, 9), env="prod")
    _sale("A1/10/2026", date(2026, 10, 20), "500")
    summary = _submit_summary(jpk_app.build_v7m(2026, 10))
    assert summary["poprzednio"] == "brak przyjętej deklaracji za 2026-09"


def test_correction_is_compared_with_corrected_declaration():
    _sale("A1/10/2026", date(2026, 10, 20), "500")
    _accept(jpk_app.build_v7m(2026, 10))
    _sale("A2/10/2026", date(2026, 10, 25), "1000")
    correction = jpk_app.build_v7m(2026, 10, correction=True, reason="Pominięta faktura A2")
    summary = _submit_summary(correction)
    assert summary["cel"] == "korekta"
    assert summary["poprzednio"]["deklaracja"].startswith("2026-10, złożona ")
    assert summary["poprzednio"]["P_38"] == "115 (zmiana +230)"
    assert "uwaga" not in summary


def test_zero_declaration_with_invoices_in_registry_is_flagged():
    built = jpk_app.build_v7m(2026, 10)  # pusty rejestr: deklaracja zerowa
    _sale("A1/10/2026", date(2026, 10, 20), "500")
    note = _submit_summary(built)["uwaga"]
    assert "rejestru za 2026-10" in note
    assert "P_38 0 zamiast 115" in note and "P_51 0 zamiast 115" in note
    assert "P_48" not in note


def test_stale_file_is_flagged_after_registry_change():
    _sale("A1/10/2026", date(2026, 10, 20), "500")
    built = jpk_app.build_v7m(2026, 10)
    _sale("A2/10/2026", date(2026, 10, 25), "1000")
    assert "P_38 115 zamiast 345" in _submit_summary(built)["uwaga"]


# --- KSeF ------------------------------------------------------------------------------


def _issue(nip: str, day: date, net: str, description: str) -> str:
    view = invoices_app.issue_invoice(
        invoices_app.IssueInvoiceInput(
            buyer_nip=nip,
            buyer_name="Klient",
            buyer_address="ul. B 2, 00-950 Warszawa",
            issue_date=day,
            net=Decimal(net),
            description=description,
        )
    )
    return view.number


def test_ksef_summary_shows_previous_invoice_of_the_same_buyer():
    october = _issue("1132191233", date(2026, 10, 31), "10000", "Programowanie: październik")
    _issue("5260250274", date(2026, 11, 5), "50", "Inny nabywca, ta sama nazwa")
    november = _issue("1132191233", date(2026, 11, 30), "12000", "Programowanie: listopad")
    _issue("1132191233", date(2026, 12, 31), "9000", "Pozniejsza faktura")
    summary = _summary(ksef_app.send_invoice, november)
    assert summary["poprzednia_faktura"] == {
        "numer": october,
        "data": "2026-10-31",
        "brutto": "12300.00 (zmiana +2460.00)",
        "opis": "Programowanie: październik",
    }


def test_ksef_summary_for_first_invoice_of_the_buyer():
    number = _issue("1132191233", date(2026, 11, 10), "1000", "Usługa")
    summary = _summary(ksef_app.send_invoice, number)
    assert summary["poprzednia_faktura"] == "brak, to pierwsza faktura dla tego nabywcy"


# --- Panel zgody w terminalu -----------------------------------------------------------


def test_summary_panel_renders_comparison_as_rows():
    err = ConfirmationRequiredError(
        action="jpk.submit",
        token="abc",
        summary={
            "poprzednio": {
                "deklaracja": "2026-09, złożona 2026-10-24",
                "P_51": "230 (zmiana -115)",
            },
            "kopia": ["a@example.com", "b@example.com"],
            "uwaga": "Opis [P_38] z nawiasami",
        },
    )
    console = Console(file=io.StringIO(), width=120, record=True)
    console.print(_summary_panel(err))
    text = console.export_text()
    assert "{" not in text and "['" not in text
    assert "230 (zmiana -115)" in text and "b@example.com" in text
    assert "Opis [P_38] z nawiasami" in text
