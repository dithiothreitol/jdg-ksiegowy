"""Potok wystawiania 1.0: pozycje, nabywca z UE, korekty, QR po KSeF, Biala lista, P_39."""

import zipfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx
from lxml import etree

from jdg_ksiegowy.app import invoices as app
from jdg_ksiegowy.app import jpk as jpk_app
from jdg_ksiegowy.app.errors import InvalidInputError
from jdg_ksiegowy.invoice.models import InvoiceKind
from jdg_ksiegowy.ksef.qr import qr_png, verification_url
from jdg_ksiegowy.registry.repository import (
    ExpenseRepository,
    FilingRepository,
    InvoiceRepository,
)
from jdg_ksiegowy.tax.pit28 import generate_pit28_report
from jdg_ksiegowy.tax.vat_period import VatLedger
from tests.helpers import ExpenseRow, save_expense

KSEF = "5260250274-20261015-0A1B2C-3D4E5F-6A"


@pytest.fixture(autouse=True)
def _seller(isolated_db, monkeypatch, tmp_path):
    from jdg_ksiegowy.config import SellerConfig, settings

    monkeypatch.setenv("SELLER_NIP", "5260250274")
    monkeypatch.setattr(settings, "seller", SellerConfig())
    for module in (app, jpk_app):
        monkeypatch.setattr(module, "DATA_DIR", tmp_path / "data")


def _issue(**kw) -> app.InvoiceView:
    base = {
        "buyer_nip": "1132191233",
        "buyer_name": "Klient",
        "buyer_address": "ul. B 2, 00-950 Warszawa",
        "issue_date": date(2026, 10, 15),
    }
    return app.issue_invoice(app.IssueInvoiceInput(**{**base, **kw}))


def test_multi_item_multi_rate_with_gtu():
    view = _issue(
        items=[
            app.ItemInput(
                description="Wdrozenie",
                quantity=Decimal("10"),
                unit="h",
                unit_price_net=Decimal("150"),
                gtu="GTU_12",
            ),
            app.ItemInput(
                description="Ksiazka", unit_price_net=Decimal("100"), vat_rate=Decimal("5")
            ),
        ]
    )
    assert (view.net, view.vat, view.gross) == (Decimal("1600"), Decimal("350"), Decimal("1950"))
    xml = etree.parse(view.xml_path).getroot()
    assert [r.findtext("{*}P_12") for r in xml.iter("{*}FaWiersz")] == ["23", "5"]

    built = jpk_app.build_v7m(2026, 10)
    assert built.xsd_valid and built.vat_due == Decimal("350")
    row = etree.parse(built.file_path).getroot().find(".//{*}SprzedazWiersz")
    assert row.findtext("{*}GTU_12") == "1"


def test_eu_buyer_service_np_goes_to_k11_and_k12():
    view = _issue(
        buyer_nip="",
        buyer_country="DE",
        buyer_eu_vat="DE811569869",
        buyer_name="Kunde GmbH",
        buyer_address="Hauptstr. 1, Berlin",
        items=[
            app.ItemInput(description="Consulting", unit_price_net=Decimal("2000"), vat_code="NP")
        ],
    )
    assert view.vat == Decimal("0") and view.buyer_country == "DE"
    built = jpk_app.build_v7m(2026, 10)
    root = etree.parse(built.file_path).getroot()
    assert built.xsd_valid
    assert root.findtext(".//{*}P_11") == "2000" and root.findtext(".//{*}P_12") == "2000"
    assert root.findtext(".//{*}SprzedazWiersz/{*}NrKontrahenta") == "DE811569869"


def test_items_and_net_are_mutually_exclusive():
    with pytest.raises(InvalidInputError, match="nie oba"):
        _issue(net=Decimal("10"), items=[app.ItemInput(description="x", unit_price_net=1)])


def test_decreasing_correction_lands_in_correction_period():
    original = _issue(net=Decimal("1000"), description="Usluga")
    InvoiceRepository().mark_sent_ksef(original.number, reference="R", ksef_number=KSEF)

    kor = app.correct_invoice(
        original.number,
        [app.ItemInput(description="Rabat", unit_price_net=Decimal("-200"))],
        reason="Rabat posprzedazowy",
        issue_date=date(2026, 11, 5),
    )
    assert kor.kind == "KOR" and kor.number == "KOR1/11/2026"
    assert (kor.net, kor.vat, kor.sale_date) == (Decimal("-200"), Decimal("-46"), date(2026, 11, 5))
    stored = InvoiceRepository().get(kor.number)
    assert stored.kind is InvoiceKind.KOR and stored.corrected_ksef_number == KSEF
    fa = etree.parse(kor.xml_path).getroot()
    assert fa.findtext(".//{*}RodzajFaktury") == "KOR"
    assert fa.findtext(".//{*}NrKSeFFaKorygowanej") == KSEF

    october = jpk_app.build_v7m(2026, 10)
    november = jpk_app.build_v7m(2026, 11)
    assert (october.vat_due, november.vat_due) == (Decimal("230"), Decimal("-46"))
    assert november.xsd_valid, november.xsd_errors
    row = etree.parse(november.file_path).getroot().find(".//{*}SprzedazWiersz")
    assert row.findtext("{*}DowodSprzedazy") == "KOR1/11/2026"
    assert row.findtext("{*}K_19") == "-200.00" and row.find("{*}DataSprzedazy") is None

    pit = generate_pit28_report(2026)
    assert pit.annual_sales_net == Decimal("800")


def test_increasing_correction_goes_to_original_period():
    original = _issue(net=Decimal("1000"), description="Usluga")
    kor = app.correct_invoice(
        original.number,
        [app.ItemInput(description="Doplata", unit_price_net=Decimal("100"))],
        reason="Blad w cenie",
        issue_date=date(2026, 11, 5),
    )
    assert kor.sale_date == date(2026, 10, 15)
    assert kor.warnings  # faktura pierwotna bez numeru KSeF


def test_cannot_correct_a_correction():
    original = _issue(net=Decimal("1000"), description="Usluga")
    kor = app.correct_invoice(
        original.number,
        [app.ItemInput(description="Rabat", unit_price_net=Decimal("-1"))],
        reason="x",
        issue_date=date(2026, 11, 5),
    )
    with pytest.raises(InvalidInputError, match="pierwotna"):
        app.correct_invoice(
            kor.number, [app.ItemInput(description="y", unit_price_net=1)], reason="y"
        )


def test_docx_gets_ksef_number_and_qr_after_sending():
    view = _issue(net=Decimal("1000"), description="Usluga")
    repo = InvoiceRepository()
    repo.mark_sent_ksef(view.number, reference="R", ksef_number=KSEF)
    app.refresh_visualization(repo.get(view.number), "test")

    with zipfile.ZipFile(view.docx_path) as docx:
        body = docx.read("word/document.xml").decode("utf-8")
        media = [docx.read(n) for n in docx.namelist() if n.startswith("word/media/")]
    assert KSEF in body
    # Obraz w dokumencie to dokladnie QR linku weryfikacji (segno jest deterministyczne)
    url = verification_url(
        "5260250274", date(2026, 10, 15), Path(view.xml_path).read_bytes(), "test"
    )
    assert url.startswith("https://qr-test.ksef.mf.gov.pl/invoice/5260250274/15-10-2026/")
    assert media == [qr_png(url)]


def test_whitelist_lookup_fills_new_buyer(monkeypatch):
    from jdg_ksiegowy.invoice import whitelist

    monkeypatch.setattr(app, "lookup", whitelist.lookup)
    subject = {
        "name": "ACME SP. Z O.O.",
        "nip": "1132191233",
        "statusVat": "Czynny",
        "workingAddress": "UL. PROSTA 1, 00-001 WARSZAWA",
        "accountNumbers": ["1"],
    }
    with respx.mock(assert_all_mocked=True) as router:
        router.get(url__startswith="https://wl-api.mf.gov.pl/api/search/nip/1132191233").mock(
            return_value=httpx.Response(200, json={"result": {"subject": subject}})
        )
        view = app.issue_invoice(
            app.IssueInvoiceInput(
                buyer_nip="1132191233",
                net=Decimal("100"),
                description="Usluga",
                issue_date=date(2026, 10, 15),
            )
        )
    assert view.buyer_name == "ACME SP. Z O.O."
    assert any("Bialej listy" in w for w in view.warnings)


def test_vat_surplus_carries_over_from_registry_and_declared_filing(tmp_path):
    save_expense(
        ExpenseRow(
            issue_date=date(2026, 9, 3), total_net=Decimal("10000"), total_vat=Decimal("2300")
        )
    )
    _issue(net=Decimal("1000"), description="Usluga")  # pazdziernik: VAT 230
    ledger = VatLedger.load()
    assert ledger.settlement((2026, 9)).nadwyzka == Decimal("2300")
    assert ledger.carry_forward((2026, 10)) == Decimal("2300")
    october = jpk_app.build_v7m(2026, 10)
    assert (october.vat_carry_forward, october.vat_to_pay, october.vat_surplus) == (
        Decimal("2300"),
        Decimal("0"),
        Decimal("2070"),
    )

    # Przyjeta deklaracja za wrzesien ma pierwszenstwo przed wyliczeniem z rejestru
    filed = tmp_path / "wrzesien.xml"
    filed.write_text(
        '<JPK xmlns="urn:x"><Deklaracja><PozycjeSzczegolowe><P_62>1000</P_62>'
        "</PozycjeSzczegolowe></Deklaracja></JPK>",
        encoding="utf-8",
    )
    repo = FilingRepository()
    f = repo.create(
        form="JPK_V7M", year=2026, month=9, purpose=1, file_path=str(filed), sha256="x", env="prod"
    )
    repo.update(f.id, status="accepted", submitted_at=datetime(2026, 10, 20))
    assert VatLedger.load().carry_forward((2026, 10)) == Decimal("1000")
    assert ExpenseRepository().list(year=2026, month=9)
    assert Path(october.file_path).exists()
