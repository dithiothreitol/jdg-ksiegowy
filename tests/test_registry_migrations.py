"""Migracje Alembic: zgodnosc ze modelami, migracja bazy v0.2 z danymi, typy kwot."""

from datetime import date
from decimal import Decimal

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from jdg_ksiegowy.registry import db
from jdg_ksiegowy.registry.types import Money


def _engine(tmp_path, name="t.db"):
    return create_engine(f"sqlite:///{tmp_path / name}")


def test_fresh_database_matches_models(tmp_path):
    engine = _engine(tmp_path)
    db.upgrade(engine)
    with engine.connect() as conn:
        diff = compare_metadata(
            MigrationContext.configure(conn, opts={"compare_type": True}), db.Base.metadata
        )
    assert diff == []


def _create_v02_schema(engine) -> None:
    """Baza w ksztalcie sprzed Alembica — jak tworzyl ja `init_db()` w 0.2 (z vat_deductible)."""
    with engine.begin() as c:
        c.execute(
            text(
                "CREATE TABLE invoices (id VARCHAR PRIMARY KEY, number VARCHAR NOT NULL UNIQUE,"
                " issue_date DATE NOT NULL, sale_date DATE NOT NULL, payment_due DATE NOT NULL,"
                " buyer_name VARCHAR NOT NULL, buyer_nip VARCHAR NOT NULL, buyer_address VARCHAR,"
                " total_net NUMERIC(10,2) NOT NULL, total_vat NUMERIC(10,2) NOT NULL,"
                " total_gross NUMERIC(10,2) NOT NULL, vat_rate NUMERIC(5,2), status VARCHAR,"
                " ksef_reference VARCHAR, ksef_sent_at DATETIME, paid_at DATETIME,"
                " docx_path VARCHAR, xml_path VARCHAR, created_at DATETIME)"
            )
        )
        c.execute(
            text(
                "CREATE TABLE expenses (id VARCHAR PRIMARY KEY, seller_name VARCHAR NOT NULL,"
                " seller_nip VARCHAR NOT NULL, seller_country VARCHAR,"
                " document_number VARCHAR NOT NULL, issue_date DATE NOT NULL,"
                " receive_date DATE NOT NULL, description VARCHAR, category VARCHAR,"
                " total_net NUMERIC(10,2) NOT NULL, total_vat NUMERIC(10,2) NOT NULL,"
                " total_gross NUMERIC(10,2) NOT NULL, vat_rate NUMERIC(5,2),"
                " vat_deductible BOOLEAN, file_path VARCHAR, notes VARCHAR, created_at DATETIME)"
            )
        )
        c.execute(
            text(
                "INSERT INTO invoices (id, number, issue_date, sale_date, payment_due, buyer_name,"
                " buyer_nip, total_net, total_vat, total_gross, vat_rate, status, ksef_reference)"
                " VALUES ('i1', 'A1/05/2026', '2026-05-31', '2026-05-31', '2026-06-14', 'Klient',"
                " '5260250274', 10500.29, 2415.07, 12915.36, 23, 'paid', '20260531-EE-REF')"
            )
        )
        c.execute(
            text(
                "INSERT INTO expenses (id, seller_name, seller_nip, seller_country,"
                " document_number, issue_date, receive_date, total_net, total_vat, total_gross,"
                " vat_rate, vat_deductible) VALUES ('e1', 'Hetzner', 'DE812871812', 'DE', 'R1',"
                " '2026-05-02', '2026-05-03', 765.92, 176.16, 942.08, 23, 0)"
            )
        )


def test_v02_database_migrates_with_data(tmp_path, monkeypatch):
    import jdg_ksiegowy.registry.db as db_module
    from jdg_ksiegowy.config import settings
    from jdg_ksiegowy.registry.repository import ExpenseRepository, InvoiceRepository

    path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{path}")
    _create_v02_schema(engine)
    xml = tmp_path / "faktura.xml"
    xml.write_text(
        '<Faktura xmlns="http://crd.gov.pl/wzor/2025/06/25/13775/"><Fa>'
        "<FaWiersz><P_7>Konsultacje</P_7><P_8A>h</P_8A><P_8B>10</P_8B><P_9A>1050.029</P_9A>"
        "<P_12>23</P_12></FaWiersz>"
        "<FaWiersz><P_7>Dojazd</P_7><P_8B>1</P_8B><P_9A>0</P_9A><P_12>23</P_12></FaWiersz>"
        "</Fa></Faktura>",
        encoding="utf-8",
    )
    with engine.begin() as c:
        c.execute(text("UPDATE invoices SET xml_path = :p"), {"p": str(xml)})
    engine.dispose()

    # Sciezka produkcyjna: silnik z PRAGMA foreign_keys=ON (regresja: kaskada przy
    # przebudowie tabeli `invoices` kasowala pozycje faktur).
    monkeypatch.setattr(settings, "db_url", f"sqlite:///{path}")
    monkeypatch.setattr(db_module, "_engine", None)
    monkeypatch.setattr(db_module, "_SessionFactory", None)
    db_module.init_db()

    engine = db_module.get_engine()
    tables = set(inspect(engine).get_table_names())
    assert {"invoice_items", "filings", "audit_log", "tax_payments", "contracts"} <= tables
    with engine.connect() as c:
        assert c.execute(text("SELECT total_net FROM invoices")).scalar() == 1050029
        assert c.execute(text("SELECT vat_deduction_pct FROM expenses")).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM invoice_items")).scalar() == 2
        assert c.execute(text("PRAGMA foreign_keys")).scalar() == 1  # przywrocone po migracji

    inv = InvoiceRepository().get("A1/05/2026")
    assert inv.total_net == Decimal("10500.29")
    assert inv.total_vat == Decimal("2415.07")
    assert [(i.description, i.quantity, i.unit) for i in inv.items] == [
        ("Konsultacje", Decimal("10"), "h"),
        ("Dojazd", Decimal("1"), "usl."),
    ]
    assert inv.items[0].vat_rate == Decimal("23.00")
    # stary numer referencyjny zostaje numerem wysylki, NIE numerem KSeF
    assert inv.ksef_reference == "20260531-EE-REF"
    assert inv.ksef_number is None

    (exp,) = ExpenseRepository().list(year=2026, month=5)
    assert exp.total_net == Decimal("765.92") and exp.vat_deduction_pct == Decimal("0.00")
    assert exp.reverse_charge is False


def test_v02_codes_in_fa3_become_item_vat_codes(tmp_path, monkeypatch):
    """P_12 'np II' / '0 WDT' z FA(3) 0.x -> kody NP / 0_WDT (a nie stawka 0 bez kodu)."""
    import jdg_ksiegowy.registry.db as db_module
    from jdg_ksiegowy.config import settings
    from jdg_ksiegowy.registry.repository import InvoiceRepository

    path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{path}")
    _create_v02_schema(engine)
    xml = tmp_path / "faktura_ue.xml"
    xml.write_text(
        '<Faktura xmlns="http://crd.gov.pl/wzor/2025/06/25/13775/"><Fa>'
        "<FaWiersz><P_7>Dev</P_7><P_8B>1</P_8B><P_9A>5000</P_9A><P_12>np II</P_12></FaWiersz>"
        "<FaWiersz><P_7>Towar</P_7><P_8B>1</P_8B><P_9A>300</P_9A><P_12>0 WDT</P_12></FaWiersz>"
        "</Fa></Faktura>",
        encoding="utf-8",
    )
    with engine.begin() as c:
        c.execute(
            text(
                "UPDATE invoices SET xml_path = :p, total_net = 5300, total_vat = 0,"
                " total_gross = 5300, vat_rate = 0"
            ),
            {"p": str(xml)},
        )
    engine.dispose()
    monkeypatch.setattr(settings, "db_url", f"sqlite:///{path}")
    monkeypatch.setattr(db_module, "_engine", None)
    monkeypatch.setattr(db_module, "_SessionFactory", None)
    db_module.init_db()

    inv = InvoiceRepository().get("A1/05/2026")
    assert [(i.description, i.vat_code, i.vat_rate) for i in inv.items] == [
        ("Dev", "NP", Decimal("0")),
        ("Towar", "0_WDT", Decimal("0")),
    ]


def test_migration_is_idempotent(tmp_path):
    engine = _engine(tmp_path)
    db.upgrade(engine)
    db.upgrade(engine)  # drugie wywolanie nic nie robi
    with engine.connect() as c:
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0003"


@pytest.mark.parametrize(
    ("value", "stored"),
    [(Decimal("0.29"), 29), (Decimal("10500.005"), 1050001), ("1.10", 110), (0.1, 10)],
)
def test_money_round_trip(value, stored):
    m = Money()
    assert m.process_bind_param(value, None) == stored
    assert m.process_result_value(stored, None) == Decimal(stored) / 100


def test_repository_round_trip_keeps_items_and_dates(isolated_db):
    from jdg_ksiegowy.invoice.models import Buyer, Invoice, LineItem
    from jdg_ksiegowy.registry.repository import InvoiceRepository

    inv = Invoice(
        number="A1/11/2026",
        issue_date=date(2026, 11, 30),
        sale_date=date(2026, 11, 30),
        period_from=date(2026, 11, 1),
        period_to=date(2026, 11, 30),
        payment_due=date(2026, 12, 14),
        buyer=Buyer(name="DE GmbH", address="Berlin", country_code="DE", eu_vat_number="DE1"),
        items=[
            LineItem(
                description="a",
                quantity=Decimal("2.5"),
                unit_price_net=Decimal("100.10"),
                vat_rate=Decimal("23"),
                gtu="GTU_12",
            ),
            LineItem(description="b", unit_price_net=Decimal("10"), vat_rate=Decimal("8")),
        ],
    )
    repo = InvoiceRepository()
    repo.save(inv)
    got = repo.get("A1/11/2026")

    assert got.items == inv.items
    assert got.total_net == inv.total_net == Decimal("260.25")
    assert got.buyer.country_code == "DE" and got.buyer.eu_vat_number == "DE1"
    assert (got.period_from, got.period_to) == (inv.period_from, inv.period_to)
    assert repo.next_number(11, 2026) == "A2/11/2026"


def test_list_by_income_uses_earlier_of_sale_and_issue(isolated_db):
    from jdg_ksiegowy.registry.repository import InvoiceRepository
    from tests.helpers import InvoiceRow, save_invoice

    save_invoice(
        InvoiceRow(
            number="X/1",
            issue_date=date(2027, 1, 3),
            sale_date=date(2026, 12, 20),
            total_net=Decimal("100"),
        )
    )
    repo = InvoiceRepository()
    assert [i.number for i in repo.list(year=2026, by="income")] == ["X/1"]
    assert repo.list(year=2026, by="issue_date") == []
