"""Testy platnosci — oznaczanie zaplaty, import CSV, dopasowanie przelewow."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from jdg_ksiegowy.invoice.models import Buyer, Invoice, InvoiceStatus, LineItem
from jdg_ksiegowy.registry.payments import BankRow, match_payments, parse_bank_csv
from jdg_ksiegowy.registry.repository import InvoiceNotFoundError, InvoiceRepository


@pytest.fixture(autouse=True)
def _autouse_isolated_db(isolated_db):
    """Wymus izolacje DB dla wszystkich testow w tym pliku (conftest.isolated_db)."""


def _inv(number: str, gross: Decimal, due: date, paid: bool = False) -> Invoice:
    inv = Invoice(
        id=f"id-{number}",
        number=number,
        issue_date=date(2026, 4, 1),
        sale_date=date(2026, 4, 1),
        payment_due=due,
        buyer=Buyer(name="Klient", nip="5260250274", address="ul. X 1"),
        items=[
            LineItem(
                description="usl",
                unit_price_net=(gross / Decimal("1.23")).quantize(Decimal("0.01")),
                vat_rate=Decimal("23"),
            )
        ],
        paid_at=datetime.now() if paid else None,
        status=InvoiceStatus.PAID if paid else InvoiceStatus.GENERATED,
    )
    InvoiceRepository().save(inv)
    return InvoiceRepository().get(number)


class TestMarkPaid:
    def test_marks_invoice_as_paid(self):
        _inv("A1/04/2026", Decimal("1230"), date(2026, 4, 30))
        InvoiceRepository().mark_paid("A1/04/2026", datetime(2026, 4, 25))
        inv = InvoiceRepository().get("A1/04/2026")
        assert inv.status is InvoiceStatus.PAID
        assert inv.paid_at == datetime(2026, 4, 25)

    def test_missing_invoice_raises(self):
        with pytest.raises(InvoiceNotFoundError, match="nie istnieje"):
            InvoiceRepository().mark_paid("NIEISTNIEJACA/01/2026", datetime.now())

    def test_already_paid_raises(self):
        _inv("A2/04/2026", Decimal("1230"), date(2026, 4, 30), paid=True)
        with pytest.raises(ValueError, match="zaplacona"):
            InvoiceRepository().mark_paid("A2/04/2026", datetime.now())


class TestMatchPayments:
    def test_matches_by_invoice_number_in_description(self):
        inv = _inv("A1/04/2026", Decimal("1230"), date(2026, 4, 30))
        assert inv.total_gross == Decimal("1230.00")
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


def test_contract_invoice_number_with_hex_prefix_matches():
    """Numery faktur z kontraktow maja prefiks K + 8 znakow hex (np. Kab12cd34)."""
    inv = _inv("Kab12cd34/04/2026", Decimal("1230"), date(2026, 4, 30))
    row = BankRow(date(2026, 5, 20), Decimal("1"), "Zaplata Kab12cd34/04/2026")
    assert match_payments([row], [inv]).matched[0][1].number == "Kab12cd34/04/2026"
