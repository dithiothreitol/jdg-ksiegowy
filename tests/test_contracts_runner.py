"""Testy cyklicznych kontraktów — runner + last_working_day."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from jdg_ksiegowy.app.contracts import run as run_contracts
from jdg_ksiegowy.contracts.runner import last_working_day


@pytest.fixture(autouse=True)
def _autouse_isolated_db(isolated_db):
    """Wymuś izolację DB dla wszystkich testów w tym pliku (conftest.isolated_db)."""


def _contract(**kwargs):
    from jdg_ksiegowy.invoice.models import Buyer, Contract
    from jdg_ksiegowy.registry.repository import ContractRepository

    defaults = dict(
        id=str(uuid.uuid4()),
        buyer=Buyer(name="Klient", nip="5260250274", address="ul. X 1"),
        description="Usluga IT",
        net_amount=Decimal("2000"),
        vat_rate=Decimal("23"),
        cycle="monthly",
        day_of_month=-1,
        auto_send_ksef=False,
        auto_send_email=False,
        active=True,
    )
    defaults.update(kwargs)
    contract = Contract(**defaults)
    ContractRepository().save(contract)
    return contract


class TestLastWorkingDay:
    def test_april_2026(self):
        d = last_working_day(2026, 4)
        assert d == date(2026, 4, 30)  # czwartek
        assert d.weekday() < 5

    def test_january_2026(self):
        d = last_working_day(2026, 1)
        assert d == date(2026, 1, 30)  # piątek (31 = sobota)
        assert d.weekday() < 5

    def test_december_2026(self):
        d = last_working_day(2026, 12)
        assert d == date(2026, 12, 31)  # czwartek
        assert d.weekday() < 5

    def test_skips_public_holiday(self):
        # 31.10.2027 to niedziela, 30.10 sobota -> 29.10 (piatek)
        assert last_working_day(2027, 10) == date(2027, 10, 29)


class TestRunContracts:
    def test_no_contracts_no_invoices(self):
        result = run_contracts(today=date(2026, 4, 30))
        assert result.generated == []

    def test_contract_fires_on_last_working_day(self):
        _contract(day_of_month=-1)
        result = run_contracts(today=date(2026, 4, 30))
        assert len(result.generated) == 1
        assert "04/2026" in result.generated[0]

    def test_contract_does_not_fire_on_wrong_day(self):
        _contract(day_of_month=-1)
        result = run_contracts(today=date(2026, 4, 29))
        assert result.generated == []

    def test_contract_fires_on_specific_day(self):
        _contract(day_of_month=15)
        result = run_contracts(today=date(2026, 4, 15))
        assert len(result.generated) == 1

    def test_idempotent_same_day_twice(self):
        _contract(day_of_month=-1)
        run_contracts(today=date(2026, 4, 30))
        result2 = run_contracts(today=date(2026, 4, 30))
        # Drugi raz nie generuje nowej faktury
        assert result2.generated == []

    def test_inactive_contract_skipped(self):
        _contract(day_of_month=-1, active=False)
        result = run_contracts(today=date(2026, 4, 30))
        assert result.generated == []

    def test_invoice_saved_to_db(self):
        from jdg_ksiegowy.registry.repository import InvoiceRepository

        _contract(day_of_month=10)
        run_contracts(today=date(2026, 4, 10))
        invoices = InvoiceRepository().list(year=2026, month=4)
        assert len(invoices) == 1
        assert invoices[0].total_gross == Decimal("2460.00")  # 2000 + 23%
        # Ten sam potok co `invoice issue`: XML FA(3) i DOCX powstaja od razu
        assert invoices[0].xml_path and invoices[0].docx_path
