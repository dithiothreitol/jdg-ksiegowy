"""Rejestr SQLite — modele ORM, silnik i migracje (Alembic).

Modele sa warstwa infrastruktury: logika biznesowa dostaje modele domenowe
z `registry.repository`, nie te rekordy.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Engine, ForeignKey, Index, String, Text, create_engine, event
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from jdg_ksiegowy.registry.types import DecimalText, Money, Percent


class Base(DeclarativeBase):
    pass


class BuyerRecord(Base):
    """Kontrahent zapamietany z wystawionych faktur (klucz: NIP)."""

    __tablename__ = "buyers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    nip: Mapped[str | None] = mapped_column(String, index=True)
    eu_vat_number: Mapped[str | None] = mapped_column(String, index=True)
    address: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    country_code: Mapped[str | None] = mapped_column(String, default="PL")
    default_description: Mapped[str | None] = mapped_column(String)
    default_vat_rate: Mapped[Decimal | None] = mapped_column(Percent, default=Decimal("23"))
    notes: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime | None] = mapped_column(default=datetime.now)
    last_used_at: Mapped[datetime | None] = mapped_column(default=datetime.now)


class InvoiceRecord(Base):
    """Faktura sprzedazy (VAT lub korygujaca)."""

    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    number: Mapped[str] = mapped_column(String, unique=True)
    kind: Mapped[str] = mapped_column(String, default="VAT")  # VAT | KOR
    issue_date: Mapped[date]
    sale_date: Mapped[date]
    period_from: Mapped[date | None]
    period_to: Mapped[date | None]
    payment_due: Mapped[date]
    buyer_name: Mapped[str] = mapped_column(String)
    buyer_nip: Mapped[str] = mapped_column(String)
    buyer_address: Mapped[str | None] = mapped_column(String)
    buyer_country: Mapped[str] = mapped_column(String, default="PL")
    buyer_eu_vat: Mapped[str | None] = mapped_column(String)
    buyer_email: Mapped[str | None] = mapped_column(String)
    total_net: Mapped[Decimal] = mapped_column(Money)
    total_vat: Mapped[Decimal] = mapped_column(Money)
    total_gross: Mapped[Decimal] = mapped_column(Money)
    status: Mapped[str | None] = mapped_column(String, default="generated")
    # Numer KSeF nadany fakturze (wzorzec TNumerKSeF) — trafia do JPK (NrKSeF / K_5).
    ksef_number: Mapped[str | None] = mapped_column(String, index=True)
    # Numer referencyjny wysylki w sesji KSeF — identyfikator techniczny, nie numer KSeF.
    ksef_reference: Mapped[str | None] = mapped_column(String)
    ksef_sent_at: Mapped[datetime | None]
    ksef_acquired_at: Mapped[datetime | None]
    ksef_upo_path: Mapped[str | None] = mapped_column(String)
    paid_at: Mapped[datetime | None]
    docx_path: Mapped[str | None] = mapped_column(String)
    xml_path: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text)
    corrected_number: Mapped[str | None] = mapped_column(String)
    corrected_ksef_number: Mapped[str | None] = mapped_column(String)
    corrected_issue_date: Mapped[date | None]
    correction_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(default=datetime.now)

    items: Mapped[list[InvoiceItemRecord]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceItemRecord.position",
        lazy="selectin",
    )


class InvoiceItemRecord(Base):
    """Pozycja faktury (FaWiersz)."""

    __tablename__ = "invoice_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int]
    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(DecimalText)
    unit: Mapped[str] = mapped_column(String)
    unit_price_net: Mapped[Decimal] = mapped_column(DecimalText)
    vat_rate: Mapped[Decimal] = mapped_column(Percent)
    vat_code: Mapped[str | None] = mapped_column(String)
    gtu: Mapped[str | None] = mapped_column(String)
    net: Mapped[Decimal] = mapped_column(Money)
    vat: Mapped[Decimal] = mapped_column(Money)
    gross: Mapped[Decimal] = mapped_column(Money)

    invoice: Mapped[InvoiceRecord] = relationship(back_populates="items")


class ContractRecord(Base):
    """Kontrakt cykliczny."""

    __tablename__ = "contracts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    buyer_name: Mapped[str] = mapped_column(String)
    buyer_nip: Mapped[str] = mapped_column(String)
    buyer_address: Mapped[str | None] = mapped_column(String)
    buyer_email: Mapped[str | None] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    net_amount: Mapped[Decimal] = mapped_column(Money)
    vat_rate: Mapped[Decimal | None] = mapped_column(Percent, default=Decimal("23"))
    cycle: Mapped[str | None] = mapped_column(String, default="monthly")
    day_of_month: Mapped[int | None] = mapped_column(default=-1)
    auto_send_ksef: Mapped[bool | None] = mapped_column(default=True)
    auto_send_email: Mapped[bool | None] = mapped_column(default=True)
    active: Mapped[bool | None] = mapped_column(default=True)
    created_at: Mapped[datetime | None] = mapped_column(default=datetime.now)


class ExpenseRecord(Base):
    """Faktura zakupu (koszt). Na ryczalcie nie pomniejsza podatku,
    ale VAT naliczony idzie do JPK_V7M."""

    __tablename__ = "expenses"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    seller_name: Mapped[str] = mapped_column(String)
    seller_nip: Mapped[str] = mapped_column(String)
    seller_country: Mapped[str | None] = mapped_column(String, default="PL")
    document_number: Mapped[str] = mapped_column(String)
    issue_date: Mapped[date]
    receive_date: Mapped[date]  # data wplywu — decyduje o miesiacu JPK
    description: Mapped[str | None] = mapped_column(String)
    category: Mapped[str | None] = mapped_column(String)
    total_net: Mapped[Decimal] = mapped_column(Money)
    total_vat: Mapped[Decimal] = mapped_column(Money)
    total_gross: Mapped[Decimal] = mapped_column(Money)
    vat_rate: Mapped[Decimal | None] = mapped_column(Percent, default=Decimal("23"))
    vat_deduction_pct: Mapped[Decimal] = mapped_column(Percent, default=Decimal("100"))
    reverse_charge: Mapped[bool] = mapped_column(default=False)
    file_path: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(String)
    ksef_number: Mapped[str | None] = mapped_column(String, index=True)
    created_at: Mapped[datetime | None] = mapped_column(default=datetime.now)


class TaxPaymentRecord(Base):
    """Platnosc podatkowa (ryczalt, VAT, ZUS)."""

    __tablename__ = "tax_payments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String)  # ryczalt|vat|zus_health|zus_social
    month: Mapped[int]
    year: Mapped[int]
    amount: Mapped[Decimal] = mapped_column(Money)
    due_date: Mapped[date]
    paid: Mapped[bool | None] = mapped_column(default=False)
    paid_at: Mapped[datetime | None]
    created_at: Mapped[datetime | None] = mapped_column(default=datetime.now)


class FilingRecord(Base):
    """Zlozona (lub przygotowana) deklaracja: JPK_V7M, JPK_EWP — dowod zlozenia."""

    __tablename__ = "filings"
    __table_args__ = (Index("ix_filings_period", "form", "year", "month"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    form: Mapped[str] = mapped_column(String)  # JPK_V7M | JPK_EWP
    year: Mapped[int]
    month: Mapped[int | None]
    purpose: Mapped[int]  # 1 = zlozenie, 2 = korekta
    file_path: Mapped[str] = mapped_column(String)
    sha256: Mapped[str] = mapped_column(String)
    env: Mapped[str] = mapped_column(String)  # test | prod
    status: Mapped[str] = mapped_column(String)  # prepared|submitted|accepted|rejected|error
    reference_number: Mapped[str | None] = mapped_column(String, index=True)
    status_code: Mapped[int | None]
    upo_path: Mapped[str | None] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    submitted_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class AuditRecord(Base):
    """Dziennik czynnosci zmieniajacych stan lub wysylajacych dane na zewnatrz."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(default=datetime.now, index=True)
    actor: Mapped[str] = mapped_column(String)  # cli | mcp | cron
    action: Mapped[str] = mapped_column(String)  # np. ksef.send, jpk.submit
    target: Mapped[str | None] = mapped_column(String)
    outcome: Mapped[str] = mapped_column(String)  # ok | error | refused
    detail: Mapped[str | None] = mapped_column(Text)  # JSON, bez sekretow


# --- Engine & Session ---

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None
_migrated: set[str] = set()


def get_engine() -> Engine:
    """Singleton engine z settings.db_url; SQLite w trybie WAL + klucze obce."""
    global _engine
    if _engine is None:
        from jdg_ksiegowy.config import settings

        url = settings.db_url
        if url.startswith("sqlite:///"):
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(url)
        if url.startswith("sqlite"):
            _configure_sqlite(_engine)
    return _engine


def _configure_sqlite(engine: Engine) -> None:
    """WAL: czytelnicy nie blokuja pisarzy, odpornosc na kill -9; FK: kaskada pozycji."""

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _conn_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def init_db() -> Engine:
    """Doprowadz schemat bazy do najnowszej migracji (raz na proces i URL)."""
    engine = get_engine()
    key = str(engine.url)
    if key not in _migrated:
        upgrade(engine)
        _migrated.add(key)
    return engine


def upgrade(engine: Engine, revision: str = "head") -> None:
    """Uruchom migracje Alembic do `revision` na podanym silniku."""
    from alembic import command
    from alembic.config import Config

    from jdg_ksiegowy.config import DATA_DIR

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.attributes["data_dir"] = DATA_DIR
    sqlite = engine.dialect.name == "sqlite"
    with engine.connect() as connection:
        # Tryb wsadowy Alembica przebudowuje tabele (DROP + RENAME); z wlaczonymi kluczami
        # obcymi DROP rodzica kaskadowo kasuje dzieci (pozycje faktur). PRAGMA dziala tylko
        # poza transakcja, a polaczenie wraca do puli — wiec przywracamy ON na koniec.
        if sqlite:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()  # zamyka autobegin SQLAlchemy przed transakcja migracji
        try:
            with connection.begin():
                cfg.attributes["connection"] = connection
                command.upgrade(cfg, revision)
        finally:
            if sqlite:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.commit()


def get_session() -> Session:
    """Nowa sesja (engine tworzony raz)."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionFactory()
