"""Testy raportu PIT-28."""

from datetime import date
from decimal import Decimal

import pytest

from jdg_ksiegowy.tax.pit28 import format_pit28_text, generate_pit28_report


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import jdg_ksiegowy.registry.db as db_module
    from jdg_ksiegowy.config import settings

    db_path = tmp_path / "jdg.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.setattr(db_module, "_engine", None)
    monkeypatch.setattr(db_module, "_SessionFactory", None)
    settings.mf.pesel = ""
    settings.seller.ryczalt_rate = Decimal("12")


def _inv(month: int, year: int, net: Decimal):
    from jdg_ksiegowy.registry.db import InvoiceRecord, init_db, save_invoice

    init_db()
    save_invoice(
        InvoiceRecord(
            id=f"i-{month}-{year}-{net}",
            number=f"A/{month:02d}/{year}",
            issue_date=date(year, month, 15),
            sale_date=date(year, month, 15),
            payment_due=date(year, month, 28),
            buyer_name="Klient",
            buyer_nip="5260250274",
            total_net=net,
            total_vat=net * Decimal("0.23"),
            total_gross=net * Decimal("1.23"),
            vat_rate=Decimal("23"),
        )
    )


class TestPIT28Report:
    def test_empty_db_returns_zero_sums(self):
        from jdg_ksiegowy.registry.db import init_db

        init_db()
        report = generate_pit28_report(2025)
        assert report.annual_sales_net == Decimal("0")
        assert report.annual_ryczalt == Decimal("0")

    def test_single_invoice_aggregated_correctly(self):
        _inv(3, 2025, Decimal("10000"))
        report = generate_pit28_report(2025)
        assert report.annual_sales_net == Decimal("10000")
        assert report.annual_ryczalt == Decimal("1200.00")

    def test_multiple_months(self):
        _inv(1, 2025, Decimal("5000"))
        _inv(2, 2025, Decimal("8000"))
        _inv(3, 2025, Decimal("7000"))
        report = generate_pit28_report(2025)
        assert report.annual_sales_net == Decimal("20000")
        # 12% * 20000 = 2400
        assert report.annual_ryczalt == Decimal("2400.00")

    def test_only_requested_year(self):
        _inv(12, 2024, Decimal("10000"))  # poprzedni rok — nie wliczamy
        _inv(1, 2025, Decimal("5000"))
        report = generate_pit28_report(2025)
        assert report.annual_sales_net == Decimal("5000")

    def test_annual_ryczalt_rounded(self):
        _inv(1, 2025, Decimal("1001"))
        report = generate_pit28_report(2025)
        # 1001 * 12% = 120.12 → zaokrąglone do 120
        assert report.annual_ryczalt_rounded == Decimal("120")

    def test_monthly_breakdown_has_12_months(self):
        _inv(6, 2025, Decimal("1000"))
        report = generate_pit28_report(2025)
        assert len(report.monthly) == 12

    def test_monthly_breakdown_correct_month(self):
        _inv(6, 2025, Decimal("3000"))
        report = generate_pit28_report(2025)
        june = next(m for m in report.monthly if m.month == 6)
        assert june.sales_net == Decimal("3000")
        assert june.ryczalt == Decimal("360.00")

    def test_format_text_contains_totals(self):
        _inv(4, 2025, Decimal("10000"))
        report = generate_pit28_report(2025)
        text = format_pit28_text(report)
        assert "10000.00" in text
        assert "1200.00" in text
        assert "2025" in text
