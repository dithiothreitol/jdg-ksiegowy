"""SQLite registry — przechowywanie faktur, kontraktów, historii."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Engine,
    Integer,
    Numeric,
    String,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from jdg_ksiegowy.config import DATA_DIR


class Base(DeclarativeBase):
    pass


class InvoiceRecord(Base):
    """Rekord faktury w rejestrze."""

    __tablename__ = "invoices"

    id = Column(String, primary_key=True)
    number = Column(String, nullable=False, unique=True)
    issue_date = Column(Date, nullable=False)
    sale_date = Column(Date, nullable=False)
    payment_due = Column(Date, nullable=False)
    buyer_name = Column(String, nullable=False)
    buyer_nip = Column(String, nullable=False)
    buyer_address = Column(String)
    total_net = Column(Numeric(10, 2), nullable=False)
    total_vat = Column(Numeric(10, 2), nullable=False)
    total_gross = Column(Numeric(10, 2), nullable=False)
    vat_rate = Column(Numeric(5, 2), default=23)  # przechowywana stawka VAT
    status = Column(String, default="draft")  # draft|generated|sent_ksef|paid|overdue
    ksef_reference = Column(String)
    ksef_sent_at = Column(DateTime)
    paid_at = Column(DateTime)
    docx_path = Column(String)
    xml_path = Column(String)
    created_at = Column(DateTime, default=datetime.now)


class ContractRecord(Base):
    """Rekord kontraktu cyklicznego."""

    __tablename__ = "contracts"

    id = Column(String, primary_key=True)
    buyer_name = Column(String, nullable=False)
    buyer_nip = Column(String, nullable=False)
    buyer_address = Column(String)
    buyer_email = Column(String)
    description = Column(String, nullable=False)
    net_amount = Column(Numeric(10, 2), nullable=False)
    vat_rate = Column(Numeric(5, 2), default=23)
    cycle = Column(String, default="monthly")
    day_of_month = Column(Integer, default=-1)
    auto_send_ksef = Column(Boolean, default=True)
    auto_send_email = Column(Boolean, default=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)


class TaxPaymentRecord(Base):
    """Rekord płatności podatkowej (ryczałt, VAT, ZUS)."""

    __tablename__ = "tax_payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String, nullable=False)  # ryczalt|vat|zus_health
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    due_date = Column(Date, nullable=False)
    paid = Column(Boolean, default=False)
    paid_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)


# --- Engine & Session (singleton) ---

DB_PATH = DATA_DIR / "jdg_ksiegowy.db"
_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None


def get_engine() -> Engine:
    """Zwróć singleton engine (tworzony raz)."""
    global _engine
    if _engine is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
    return _engine


def init_db() -> Engine:
    """Utwórz tabele jeśli nie istnieją. Wywołaj raz przy starcie."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    return engine


def get_session() -> Session:
    """Zwróć nową sesję (engine tworzony raz, nie na każde wywołanie)."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine())
    return _SessionFactory()


# --- CRUD ---


def save_invoice(record: InvoiceRecord) -> InvoiceRecord:
    with get_session() as session:
        session.merge(record)
        session.commit()
    return record


def get_invoices(month: int | None = None, year: int | None = None) -> list[InvoiceRecord]:
    with get_session() as session:
        q = session.query(InvoiceRecord)
        if month and year:
            if month < 12:
                end_date = date(year, month + 1, 1)
            else:
                end_date = date(year + 1, 1, 1)
            q = q.filter(
                InvoiceRecord.issue_date >= date(year, month, 1),
                InvoiceRecord.issue_date < end_date,
            )
        return q.order_by(InvoiceRecord.issue_date.desc()).all()


def get_next_invoice_number(month: int, year: int) -> str:
    """Generuj następny numer faktury: A{seq}/MM/RRRR."""
    with get_session() as session:
        count = (
            session.query(InvoiceRecord)
            .filter(InvoiceRecord.number.like(f"A%/{month:02d}/{year}"))
            .count()
        )
    seq = count + 1
    return f"A{seq}/{month:02d}/{year}"


def save_contract(record: ContractRecord) -> ContractRecord:
    with get_session() as session:
        session.merge(record)
        session.commit()
    return record


def get_active_contracts() -> list[ContractRecord]:
    with get_session() as session:
        return session.query(ContractRecord).filter(ContractRecord.active.is_(True)).all()


def save_tax_payment(record: TaxPaymentRecord) -> TaxPaymentRecord:
    with get_session() as session:
        session.add(record)
        session.commit()
    return record
