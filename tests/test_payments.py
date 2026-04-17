"""Testy śledzenia płatności — mark_paid, CSV import, dopasowanie."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from jdg_ksiegowy.registry.payments import (
    BankRow,
    mark_paid,
    match_payments,
    parse_bank_csv,
)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import jdg_ksiegowy.registry.db as db_module
    from jdg_ksiegowy.config import settings

    db_path = tmp_path / "jdg.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.setattr(db_module, "_engine", None)
    monkeypatch.setattr(db_module, "_SessionFactory", None)
    settings.mf.pesel = ""


def _inv(number: str, gross: Decimal, due: date, paid: bool = False):
    from jdg_ksiegowy.registry.db import InvoiceRecord, init_db, save_invoice

    init_db()
    rec = InvoiceRecord(
        id=f"id-{number}",
        number=number,
        issue_date=date(2026, 4, 1),
        sale_date=date(2026, 4, 1),
        payment_due=due,
        buyer_name="Klient",
        buyer_nip="5260250274",
        total_net=gross / Decimal("1.23"),
        total_vat=gross - gross / Decimal("1.23"),
        total_gross=gross,
        vat_rate=Decimal("23"),
        paid_at=datetime.now() if paid else None,
        status="paid" if paid else "generated",
    )
    save_invoice(rec)
    return rec


class TestMarkPaid:
    def test_marks_invoice_as_paid(self):
        _inv("A1/04/2026", Decimal("1230"), date(2026, 4, 30))
        result = mark_paid("A1/04/2026")
        assert result.success is True
        assert result.error == ""

    def test_returns_error_for_missing_invoice(self):
        from jdg_ksiegowy.registry.db import init_db

        init_db()
        result = mark_paid("NIEISTNIEJACA/01/2026")
        assert result.success is False
        assert "nie istnieje" in result.error.lower()

    def test_returns_error_if_already_paid(self):
        _inv("A2/04/2026", Decimal("1230"), date(2026, 4, 30), paid=True)
        result = mark_paid("A2/04/2026")
        assert result.success is False
        assert "zaplacona" in result.error.lower()

    def test_sets_paid_at_timestamp(self):
        from jdg_ksiegowy.registry.db import get_invoices, init_db

        init_db()
        _inv("A3/04/2026", Decimal("1230"), date(2026, 4, 30))
        ts = datetime(2026, 4, 25, 12, 0, 0)
        mark_paid("A3/04/2026", paid_at=ts)
        inv = get_invoices()[0]
        assert inv.paid_at is not None


class TestMatchPayments:
    def test_matches_by_invoice_number_in_description(self):
        inv = _inv("A1/04/2026", Decimal("1230"), date(2026, 4, 30))
        row = BankRow(date(2026, 4, 26), Decimal("1230"), "Przelew za A1/04/2026 uslugi IT")
        result = match_payments([row], [inv])
        assert len(result.matched) == 1
        assert result.matched[0][1].number == "A1/04/2026"
        assert result.unmatched_bank == []
        assert result.unmatched_invoices == []

    def test_matches_by_amount_and_date(self):
        inv = _inv("A2/04/2026", Decimal("2460"), date(2026, 4, 30))
        row = BankRow(date(2026, 4, 28), Decimal("2460"), "Przelew od firmy XYZ")
        result = match_payments([row], [inv])
        assert len(result.matched) == 1

    def test_no_match_for_wrong_amount(self):
        inv = _inv("A3/04/2026", Decimal("1230"), date(2026, 4, 30))
        row = BankRow(date(2026, 4, 26), Decimal("999"), "Cokolwiek")
        result = match_payments([row], [inv])
        assert len(result.matched) == 0
        assert len(result.unmatched_bank) == 1
        assert len(result.unmatched_invoices) == 1

    def test_skips_already_paid(self):
        inv = _inv("A4/04/2026", Decimal("1230"), date(2026, 4, 30), paid=True)
        row = BankRow(date(2026, 4, 26), Decimal("1230"), "Przelew za A4/04/2026")
        result = match_payments([row], [inv])
        assert len(result.matched) == 0

    def test_negative_amounts_skipped(self):
        inv = _inv("A5/04/2026", Decimal("1230"), date(2026, 4, 30))
        row = BankRow(date(2026, 4, 26), Decimal("-1230"), "Obciazenie")
        result = match_payments([row], [inv])
        assert len(result.matched) == 0


class TestParseBankCSV:
    def test_parses_generic_csv(self, tmp_path):
        csv_content = "date,amount,description\n2026-04-25,1230.00,Faktura A1/04/2026\n"
        f = tmp_path / "bank.csv"
        f.write_text(csv_content, encoding="utf-8")
        rows = parse_bank_csv(f)
        assert len(rows) == 1
        assert rows[0].amount == Decimal("1230.00")
        assert rows[0].transaction_date == date(2026, 4, 25)

    def test_parses_mbank_csv(self, tmp_path):
        content = (
            "#Data operacji;Opis operacji;Dane kontrahenta;Tytuł;Kwota;Waluta\n"
            "2026-04-25;Przelew;Klient ABC;A1/04/2026;1230,00;PLN\n"
        )
        f = tmp_path / "mbank.csv"
        f.write_text(content, encoding="utf-8")
        rows = parse_bank_csv(f)
        assert len(rows) == 1
        assert rows[0].amount == Decimal("1230.00")
