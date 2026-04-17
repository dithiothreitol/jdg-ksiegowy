"""Testy Dashboard: snapshot, terminy, poziomy przypomnien."""

from datetime import date
from decimal import Decimal

import pytest

from jdg_ksiegowy.status.dashboard import Dashboard, ReminderLevel


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Izoluj SQLite per-test zeby nie zaciagac faktur z innych testow."""
    import jdg_ksiegowy.registry.db as db_module
    from jdg_ksiegowy.config import settings

    db_path = tmp_path / "jdg.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.setattr(db_module, "_engine", None)
    monkeypatch.setattr(db_module, "_SessionFactory", None)
    settings.mf.pesel = ""  # neutralize config interference


def test_level_for_computes_correctly():
    assert Dashboard._level_for(-1) is ReminderLevel.OVERDUE
    assert Dashboard._level_for(0) is ReminderLevel.URGENT
    assert Dashboard._level_for(1) is ReminderLevel.URGENT
    assert Dashboard._level_for(5) is ReminderLevel.WARN
    assert Dashboard._level_for(30) is ReminderLevel.INFO


def test_snapshot_with_empty_db():
    snap = Dashboard(today=date(2026, 4, 17)).snapshot()
    assert snap.today == date(2026, 4, 17)
    assert snap.month_sales_net == Decimal("0")
    assert len(snap.unpaid_invoices) == 0
    assert len(snap.overdue_invoices) == 0
    # Standardowe terminy obecne (ryczalt/ZUS/VAT za marzec)
    labels = [r.label for r in snap.reminders]
    assert any("Ryczalt za 03/2026" in lb for lb in labels)
    assert any("ZUS zdrowotne za 03/2026" in lb for lb in labels)
    assert any("VAT + JPK_V7M za 03/2026" in lb for lb in labels)


def test_snapshot_aggregates_current_month_invoices():
    from jdg_ksiegowy.registry.db import InvoiceRecord, init_db, save_invoice

    init_db()
    save_invoice(
        InvoiceRecord(
            id="i1",
            number="A1/04/2026",
            issue_date=date(2026, 4, 5),
            sale_date=date(2026, 4, 5),
            payment_due=date(2026, 4, 30),
            buyer_name="Klient",
            buyer_nip="1234567890",
            total_net=Decimal("1000"),
            total_vat=Decimal("230"),
            total_gross=Decimal("1230"),
            vat_rate=Decimal("23"),
        )
    )
    save_invoice(
        InvoiceRecord(
            id="i2",
            number="A2/04/2026",
            issue_date=date(2026, 4, 10),
            sale_date=date(2026, 4, 10),
            payment_due=date(2026, 5, 10),
            buyer_name="K2",
            buyer_nip="1234567890",
            total_net=Decimal("500"),
            total_vat=Decimal("115"),
            total_gross=Decimal("615"),
            vat_rate=Decimal("23"),
        )
    )

    snap = Dashboard(today=date(2026, 4, 17)).snapshot()
    assert snap.month_sales_net == Decimal("1500")
    assert snap.month_sales_vat == Decimal("345")


def test_overdue_invoices_flagged():
    from jdg_ksiegowy.registry.db import InvoiceRecord, init_db, save_invoice

    init_db()
    save_invoice(
        InvoiceRecord(
            id="i-overdue",
            number="A/03/2026",
            issue_date=date(2026, 3, 1),
            sale_date=date(2026, 3, 1),
            payment_due=date(2026, 3, 15),  # 30+ dni temu
            buyer_name="Niepunktualny",
            buyer_nip="1234567890",
            total_net=Decimal("1000"),
            total_vat=Decimal("230"),
            total_gross=Decimal("1230"),
        )
    )

    snap = Dashboard(today=date(2026, 4, 17)).snapshot()
    assert len(snap.overdue_invoices) == 1
    assert snap.overdue_invoices[0].number == "A/03/2026"
    # Reminder w liscie z level=OVERDUE
    overdue_rem = [r for r in snap.reminders if r.level is ReminderLevel.OVERDUE]
    assert any("Niepunktualny" in r.label for r in overdue_rem)


def test_upcoming_invoice_within_7_days_is_warn():
    from jdg_ksiegowy.registry.db import InvoiceRecord, init_db, save_invoice

    init_db()
    save_invoice(
        InvoiceRecord(
            id="i-soon",
            number="A/04/2026",
            issue_date=date(2026, 4, 10),
            sale_date=date(2026, 4, 10),
            payment_due=date(2026, 4, 20),  # 3 dni od "today"=17
            buyer_name="Soon",
            buyer_nip="1234567890",
            total_net=Decimal("1000"),
            total_vat=Decimal("230"),
            total_gross=Decimal("1230"),
        )
    )

    snap = Dashboard(today=date(2026, 4, 17)).snapshot()
    reminders_for_inv = [r for r in snap.reminders if "A/04/2026" in r.label]
    assert len(reminders_for_inv) == 1
    assert reminders_for_inv[0].level is ReminderLevel.WARN


def test_estimated_ryczalt_uses_previous_month():
    from jdg_ksiegowy.registry.db import InvoiceRecord, init_db, save_invoice

    init_db()
    # Marzec: 10 000 netto — ryczalt 12% = 1200
    save_invoice(
        InvoiceRecord(
            id="i-march",
            number="A/03/2026",
            issue_date=date(2026, 3, 15),
            sale_date=date(2026, 3, 15),
            payment_due=date(2026, 4, 1),
            buyer_name="X",
            buyer_nip="1234567890",
            total_net=Decimal("10000"),
            total_vat=Decimal("2300"),
            total_gross=Decimal("12300"),
        )
    )

    snap = Dashboard(today=date(2026, 4, 10)).snapshot()
    assert snap.estimated_ryczalt == Decimal("1200.00")
