"""Testy raportu PIT-28."""

from datetime import date
from decimal import Decimal

import pytest

from jdg_ksiegowy.tax.pit28 import generate_pit28_report


@pytest.fixture(autouse=True)
def _autouse_isolated_db(isolated_db):
    """Wymuś izolację DB dla wszystkich testów w tym pliku (conftest.isolated_db)."""
    from jdg_ksiegowy.config import settings

    settings.seller.ryczalt_rate = Decimal("12")


def _inv(month: int, year: int, net: Decimal):
    from tests.helpers import InvoiceRow, save_invoice

    save_invoice(
        InvoiceRow(
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
        # 1001 * 12% = 120.12 -> pelne zlote (art. 63 Ordynacji)
        assert report.annual_ryczalt == Decimal("120")

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

    def test_deductions_and_advances_from_payment_ledger(self):
        """Zaplacone skladki zmniejszaja podstawe; zaplacone zaliczki — kwote do zaplaty."""
        from datetime import datetime

        from jdg_ksiegowy.registry.repository import TaxPayment, TaxPaymentRepository

        _inv(4, 2025, Decimal("10000"))
        repo = TaxPaymentRepository()
        paid = datetime(2025, 4, 18)
        repo.record(TaxPayment("zus_health", 2025, 3, Decimal("830.58"), date(2025, 4, 22), paid))
        repo.record(TaxPayment("zus_social", 2025, 3, Decimal("1000.00"), date(2025, 4, 22), paid))
        repo.record(
            TaxPayment(
                "ryczalt", 2025, 4, Decimal("1000"), date(2025, 5, 20), datetime(2025, 5, 19)
            )
        )

        report = generate_pit28_report(2025)
        # odliczenie: 1000 + 50% * 830.58 = 1415.29 -> podstawa 8585 -> ryczalt 1030.20 -> 1030
        assert report.annual_deductions == Decimal("1415.29")
        assert report.annual_base == Decimal("8585")
        assert report.annual_ryczalt == Decimal("1030")
        april = next(m for m in report.monthly if m.month == 4)
        assert april.deductions == Decimal("1415.29") and april.ryczalt == Decimal("1030")
        assert report.advances_paid == Decimal("1000")
        assert report.to_pay == Decimal("30")
        assert report.deadline == date(2026, 4, 30)
