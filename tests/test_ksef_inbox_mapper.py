"""Testy mappera KSeF -> ExpenseRecord, chunkowania query_inbox i migracji.

Zero sieci: SDK (all_metadata) jest mockowane, metadane to lekkie SimpleNamespace.
"""

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from lxml import etree

from jdg_ksiegowy.expenses.ksef_mapper import (
    metadata_to_record,
    needs_manual_review,
)
from jdg_ksiegowy.expenses.models import Expense, ExpenseCategory
from jdg_ksiegowy.tax.jpk import TNS, generate_jpk_v7m


def _meta(**over):
    """Fake InvoiceMetadata — pola, ktore czyta mapper/query_inbox."""
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


# --- mapper: kwoty, daty, stawka ---


def test_amounts_and_dates_mapped():
    rec = metadata_to_record(_meta())
    assert rec.total_net == Decimal("147.06")
    assert rec.total_vat == Decimal("33.83")
    assert rec.total_gross == Decimal("180.89")
    # receive_date = data przyjecia w KSeF (decyduje o miesiacu JPK), NIE issue_date
    assert rec.receive_date == date(2026, 5, 26)
    assert rec.issue_date == date(2026, 5, 25)
    assert rec.ksef_number == "5261040567-20260525-AAAAAA-01"


def test_vat_rate_derived_from_aggregates():
    # 33.83 / 147.06 * 100 ~= 23
    assert metadata_to_record(_meta()).vat_rate == Decimal("23")


def test_vat_rate_zero_when_net_zero():
    rec = metadata_to_record(_meta(net_amount=0.0, vat_amount=0.0, gross_amount=0.0))
    assert rec.vat_rate == Decimal("0")


def test_multi_rate_flagged_in_notes():
    # 10/100 -> 10% (poza {0,5,8,23}) => nota
    rec = metadata_to_record(_meta(net_amount=100.0, vat_amount=10.0, gross_amount=110.0))
    assert rec.vat_rate == Decimal("10")
    assert "multi-rate" in (rec.notes or "")


def test_fuel_8pct_not_flagged():
    rec = metadata_to_record(_meta(net_amount=100.0, vat_amount=8.0, gross_amount=108.0))
    assert rec.vat_rate == Decimal("8")
    assert "multi-rate" not in (rec.notes or "")


# --- mapper: kategoria, deduction, id ---


def test_fuel_category_inferred_but_deduction_stays_100():
    rec = metadata_to_record(_meta())  # Shell -> paliwo
    assert rec.category == ExpenseCategory.PALIWO.value
    # KLUCZOWE: nie auto-50; default 100, tylko podpowiedz w notes
    assert rec.vat_deduction_pct == Decimal("100")
    assert "50" in (rec.notes or "")


def test_non_fuel_category_inne():
    rec = metadata_to_record(_meta(seller=SimpleNamespace(nip="1111111111", name="PGE Obrot SA")))
    assert rec.category == ExpenseCategory.INNE.value


def test_category_override():
    rec = metadata_to_record(_meta(), category=ExpenseCategory.SPRZET)
    assert rec.category == ExpenseCategory.SPRZET.value


def test_deduction_override_no_fuel_hint():
    rec = metadata_to_record(_meta(), vat_deduction_pct=Decimal("50"))
    assert rec.vat_deduction_pct == Decimal("50")
    assert "rozwaz" not in (rec.notes or "")  # podpowiedz tylko gdy zostalo 100


def test_id_follows_nip_document_convention():
    rec = metadata_to_record(_meta())
    assert rec.id == "5261040567-FV/2026/05/123"


def test_id_fallback_to_ksef_number_when_no_nip():
    rec = metadata_to_record(_meta(seller=SimpleNamespace(nip="", name="Zagraniczny")))
    assert rec.id == "5261040567-20260525-AAAAAA-01"
    assert rec.seller_nip == ""


# --- needs_manual_review ---


def test_manual_review_correction():
    assert "korekta" in needs_manual_review(_meta(invoice_type="kor_zal"))


def test_manual_review_foreign_currency():
    assert "EUR" in needs_manual_review(_meta(currency="EUR"))


def test_manual_review_self_invoicing():
    assert needs_manual_review(_meta(is_self_invoicing=True)) is not None


def test_manual_review_clean_invoice_is_none():
    assert needs_manual_review(_meta()) is None


# --- query_inbox: chunkowanie + dedup + filtr typow ---


class _FakeInvoices:
    def __init__(self, pages):
        self.filters_seen = []
        self._pages = list(pages)

    def all_metadata(self, *, filters, params=None):
        self.filters_seen.append(filters)
        page = self._pages.pop(0) if self._pages else []
        return iter(page)


def _patch_authed(monkeypatch, fake_invoices):
    from jdg_ksiegowy.ksef.client import KSeFClient

    monkeypatch.setattr(
        KSeFClient,
        "_authenticated_client",
        lambda self: SimpleNamespace(invoices=fake_invoices),
    )


def test_query_inbox_chunks_long_range_and_dedups(monkeypatch):
    from jdg_ksiegowy.ksef.client import KSeFClient

    fake = _FakeInvoices(
        pages=[[_meta(ksef_number="A")], [_meta(ksef_number="B")], [_meta(ksef_number="A")]]
    )
    _patch_authed(monkeypatch, fake)

    out = KSeFClient().query_inbox(date(2026, 1, 1), date(2026, 5, 31))

    assert len(fake.filters_seen) == 3  # 5 mies. -> 3 okna <=2 mies.
    assert [m.ksef_number for m in out] == ["A", "B"]  # A z okna 1 i 3 -> raz


def test_query_inbox_default_excludes_corrections(monkeypatch):
    fake = _FakeInvoices(pages=[[]])
    _patch_authed(monkeypatch, fake)
    from jdg_ksiegowy.ksef.client import KSeFClient

    KSeFClient().query_inbox(date(2026, 5, 1), date(2026, 5, 31))
    assert "kor" not in fake.filters_seen[0].invoice_types


def test_query_inbox_include_corrections(monkeypatch):
    fake = _FakeInvoices(pages=[[]])
    _patch_authed(monkeypatch, fake)
    from jdg_ksiegowy.ksef.client import KSeFClient

    KSeFClient().query_inbox(date(2026, 5, 1), date(2026, 5, 31), include_corrections=True)
    assert "kor" in fake.filters_seen[0].invoice_types


def test_query_inbox_seller_nip_passed_to_filter(monkeypatch):
    fake = _FakeInvoices(pages=[[]])
    _patch_authed(monkeypatch, fake)
    from jdg_ksiegowy.ksef.client import KSeFClient

    KSeFClient().query_inbox(date(2026, 5, 1), date(2026, 5, 31), seller_nip="5261009190")
    assert fake.filters_seen[0].seller_nip == "5261009190"


# --- migracja kolumny ksef_number ---


def test_migration_adds_ksef_number_idempotent(tmp_path):
    from sqlalchemy import create_engine, inspect, text

    from jdg_ksiegowy.registry.db import _migrate_expense_add_ksef_number

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE expenses (id VARCHAR PRIMARY KEY, seller_nip VARCHAR)"))

    _migrate_expense_add_ksef_number(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("expenses")}
    assert "ksef_number" in cols

    _migrate_expense_add_ksef_number(engine)  # drugie wywolanie nie rzuca


# --- E2E (bez sieci): metadata -> mapper -> DB -> JPK_V7M ---


def _ns(t: str) -> str:
    return f"{{{TNS}}}{t}"


def _record_to_expense(r) -> Expense:
    return Expense(
        id=r.id,
        seller_name=r.seller_name,
        seller_nip=r.seller_nip,
        seller_country=r.seller_country or "PL",
        document_number=r.document_number,
        issue_date=r.issue_date,
        receive_date=r.receive_date,
        category=ExpenseCategory(r.category) if r.category else ExpenseCategory.INNE,
        total_net=Decimal(str(r.total_net)),
        total_vat=Decimal(str(r.total_vat)),
        vat_rate=Decimal(str(r.vat_rate)) if r.vat_rate else Decimal("23"),
        vat_deduction_pct=Decimal(str(r.vat_deduction_pct)),
    )


def test_e2e_ksef_invoice_lands_in_correct_jpk_month(isolated_db):
    from jdg_ksiegowy.invoice.models import Buyer, Invoice, LineItem
    from jdg_ksiegowy.registry.db import get_expenses, init_db, save_expense

    init_db()
    meta = _meta(
        ksef_number="2222222222-20260510-BBBBBB-02",
        invoice_number="K/2026/05/9",
        acquisition_date=datetime(2026, 5, 10, 9, 0),
        seller=SimpleNamespace(nip="2222222222", name="Dostawca"),
        net_amount=500.0,
        vat_amount=115.0,
        gross_amount=615.0,
    )
    save_expense(metadata_to_record(meta))

    # receive_date (10.05) -> faktura w JPK za maj, nie za kwiecien
    assert len(get_expenses(5, 2026)) == 1
    assert len(get_expenses(4, 2026)) == 0

    expenses = [_record_to_expense(r) for r in get_expenses(5, 2026)]
    inv = Invoice(
        number="S/1",
        issue_date=date(2026, 5, 1),
        sale_date=date(2026, 5, 1),
        payment_due=date(2026, 5, 15),
        buyer=Buyer(name="Klient", nip="1111111111", address="ul. X 1"),
        items=[LineItem(description="usl", unit_price_net=Decimal("1000"), vat_rate=Decimal("23"))],
    )
    xml = generate_jpk_v7m([inv], month=5, year=2026, expenses=expenses)
    root = etree.fromstring(xml.encode("utf-8"))

    zakup = root.find(f".//{_ns('ZakupWiersz')}")
    assert zakup is not None
    assert zakup.find(_ns("K_42")).text == "500.00"
    assert zakup.find(_ns("K_43")).text == "115.00"
