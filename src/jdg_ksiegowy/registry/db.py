"""SQLite registry — przechowywanie faktur, kontraktów, historii."""

from __future__ import annotations

import uuid
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
    event,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from jdg_ksiegowy.config import DATA_DIR


class Base(DeclarativeBase):
    pass


class BuyerRecord(Base):
    """Kontrahent (nabywca) — zapamiętane dane do reuse w kolejnych fakturach.

    Klucz biznesowy: NIP (PL) albo eu_vat_number (zagraniczny). Auto-upsert
    przy save_invoice() — nie trzeba przepisywać danych z poprzedniej faktury.
    """

    __tablename__ = "buyers"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    nip = Column(String, index=True)  # 10 cyfr PL; pusty dla zagranicznych
    eu_vat_number = Column(String, index=True)  # np. "DE812871812"
    address = Column(String)
    email = Column(String)
    country_code = Column(String, default="PL")
    default_description = Column(String)  # typowy opis usługi do auto-uzupełnienia
    default_vat_rate = Column(Numeric(5, 2), default=23)
    notes = Column(String)
    created_at = Column(DateTime, default=datetime.now)
    last_used_at = Column(DateTime, default=datetime.now)


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


class ExpenseRecord(Base):
    """Faktura zakupu (koszt). Na ryczalcie nie pomniejsza podatku,
    ale VAT naliczony idzie do JPK_V7M (jesli VAT-owiec)."""

    __tablename__ = "expenses"

    id = Column(String, primary_key=True)
    seller_name = Column(String, nullable=False)
    seller_nip = Column(String, nullable=False)
    seller_country = Column(String, default="PL")
    document_number = Column(String, nullable=False)  # numer faktury sprzedawcy
    issue_date = Column(Date, nullable=False)
    receive_date = Column(Date, nullable=False)  # data wplywu, decyduje o miesiacu JPK
    description = Column(String)
    category = Column(String)  # np. "uslugi obce", "materialy", "media"
    total_net = Column(Numeric(10, 2), nullable=False)
    total_vat = Column(Numeric(10, 2), nullable=False)
    total_gross = Column(Numeric(10, 2), nullable=False)
    vat_rate = Column(Numeric(5, 2), default=23)
    # Procent VAT odliczalnego: 100=pelne odliczenie, 50=auto osobowe mieszane,
    # 0=brak odliczenia (np. reprezentacja).
    vat_deduction_pct = Column(Numeric(5, 2), default=100, nullable=False)
    # Import usług / odwrotne obciążenie — nabywca sam nalicza VAT należny i odlicza go.
    reverse_charge = Column(Boolean, default=False, nullable=False)
    file_path = Column(String)  # PDF/JPG/XML zachowanego dowodu
    notes = Column(String)
    # Numer KSeF faktury zakupowej pobranej z inboxu — None dla wpisow recznych/OCR.
    # Klucz audytowy + pozwala ponownie pobrac XML i wykryc kolizje PK.
    ksef_number = Column(String, nullable=True, index=True)
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

# Ścieżka do pliku DB jest pochodną settings.db_url, ale pozostawiamy
# DB_PATH jako export do testów / skryptów backupu.
DB_PATH = DATA_DIR / "jdg_ksiegowy.db"
_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None


def get_engine() -> Engine:
    """Zwróć singleton engine (tworzony raz).

    URL bierzemy z settings.db_url (.env), z fallbackiem na lokalny SQLite.
    Dla SQLite włączamy WAL mode + synchronous=NORMAL — bezpieczne przy
    współbieżnym zapisie (skill + cron heartbeat) i odporne na crash.
    """
    global _engine
    if _engine is None:
        from jdg_ksiegowy.config import settings

        url = settings.db_url
        if url.startswith("sqlite:///"):
            db_file = url.replace("sqlite:///", "", 1)
            from pathlib import Path

            Path(db_file).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(url, echo=False)
        if url.startswith("sqlite"):
            _enable_sqlite_wal(_engine)
    return _engine


def _enable_sqlite_wal(engine: Engine) -> None:
    """Włącz WAL + synchronous=NORMAL na każdym connect.

    WAL = Write-Ahead Log: atomowe zapisy, czytelnicy nie blokują pisarzy,
    odporne na kill -9. synchronous=NORMAL = wystarczająco bezpieczne
    przy WAL, znacznie szybsze niż FULL.
    """

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _conn_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


def init_db() -> Engine:
    """Utwórz tabele jeśli nie istnieją. Wywołaj raz przy starcie."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    _migrate_expense_deduction_pct(engine)
    _migrate_expense_add_ksef_number(engine)
    _migrate_expense_add_reverse_charge(engine)
    return engine


def _migrate_expense_deduction_pct(engine: Engine) -> None:
    """Migracja: vat_deductible (bool) -> vat_deduction_pct (Numeric).

    Idempotentna: jesli stara kolumna `vat_deductible` jeszcze istnieje, dodaje
    `vat_deduction_pct` (True->100, False->0) i usuwa starą kolumne. Po wykonaniu
    przy kolejnym wywolaniu nie robi nic.
    """
    inspector = inspect(engine)
    if "expenses" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("expenses")}
    if "vat_deductible" not in cols:
        return  # Migracja juz wykonana

    with engine.begin() as conn:
        if "vat_deduction_pct" not in cols:
            conn.execute(
                text("ALTER TABLE expenses ADD COLUMN vat_deduction_pct NUMERIC(5,2) DEFAULT 100")
            )
        conn.execute(
            text(
                "UPDATE expenses SET vat_deduction_pct = "
                "CASE WHEN vat_deductible THEN 100 ELSE 0 END"
            )
        )
        # SQLite >=3.35 wspiera DROP COLUMN
        conn.execute(text("ALTER TABLE expenses DROP COLUMN vat_deductible"))


def _migrate_expense_add_ksef_number(engine: Engine) -> None:
    """Migracja: dodaj kolumne `ksef_number` do expenses (faktury z inboxu KSeF).

    Idempotentna: dodaje kolumne tylko gdy jeszcze nie istnieje. Indeks tworzy
    create_all() przy nowych bazach; przy migracji starej bazy dodajemy go recznie.
    """
    inspector = inspect(engine)
    if "expenses" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("expenses")}
    if "ksef_number" in cols:
        return  # Migracja juz wykonana

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE expenses ADD COLUMN ksef_number VARCHAR"))
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_expenses_ksef_number ON expenses (ksef_number)")
        )


def _migrate_expense_add_reverse_charge(engine: Engine) -> None:
    """Migracja: dodaj kolumne `reverse_charge` do expenses (import usług).

    Idempotentna: dodaje kolumne tylko gdy jeszcze nie istnieje (default 0).
    """
    inspector = inspect(engine)
    if "expenses" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("expenses")}
    if "reverse_charge" in cols:
        return  # Migracja juz wykonana

    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE expenses ADD COLUMN reverse_charge BOOLEAN DEFAULT 0 NOT NULL")
        )


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
        # Auto-upsert kontrahenta: zapamiętaj nabywcę po NIP do reuse
        # przy kolejnych fakturach.
        if record.buyer_nip:
            _upsert_buyer_from_invoice(session, record)
        session.commit()
    return record


def _upsert_buyer_from_invoice(session: Session, inv: InvoiceRecord) -> None:
    """Zapisz/odśwież kontrahenta na bazie wystawionej faktury (idempotent)."""
    existing = (
        session.query(BuyerRecord).filter(BuyerRecord.nip == inv.buyer_nip).one_or_none()
    )
    now = datetime.now()
    if existing is None:
        session.add(
            BuyerRecord(
                id=str(uuid.uuid4()),
                name=inv.buyer_name,
                nip=inv.buyer_nip,
                address=inv.buyer_address,
                default_vat_rate=inv.vat_rate,
                created_at=now,
                last_used_at=now,
            )
        )
    else:
        existing.name = inv.buyer_name
        if inv.buyer_address:
            existing.address = inv.buyer_address
        existing.last_used_at = now


def find_buyer_by_nip(nip: str) -> BuyerRecord | None:
    """Wyszukaj zapamiętanego kontrahenta po NIP."""
    if not nip:
        return None
    with get_session() as session:
        return session.query(BuyerRecord).filter(BuyerRecord.nip == nip).one_or_none()


def find_buyer_by_name(name: str) -> BuyerRecord | None:
    """Fuzzy-szukaj kontrahenta po nazwie (LIKE %name%)."""
    if not name:
        return None
    with get_session() as session:
        return (
            session.query(BuyerRecord)
            .filter(BuyerRecord.name.ilike(f"%{name}%"))
            .order_by(BuyerRecord.last_used_at.desc())
            .first()
        )


def save_buyer(record: BuyerRecord) -> BuyerRecord:
    with get_session() as session:
        session.merge(record)
        session.commit()
    return record


def get_invoices(
    month: int | None = None,
    year: int | None = None,
    by: str = "sale_date",
) -> list[InvoiceRecord]:
    """Pobierz faktury. Filtr 'by' decyduje wg ktorej daty:
    - 'sale_date' (default, wlasciwe dla JPK_V7M — moment obowiazku VAT wg art. 19a)
    - 'issue_date' (data wystawienia — wlasciwe dla ewidencji rocznych PIT-28)
    """
    with get_session() as session:
        q = session.query(InvoiceRecord)
        date_col = InvoiceRecord.sale_date if by == "sale_date" else InvoiceRecord.issue_date
        if month and year:
            if month < 12:
                end_date = date(year, month + 1, 1)
            else:
                end_date = date(year + 1, 1, 1)
            q = q.filter(
                date_col >= date(year, month, 1),
                date_col < end_date,
            )
        return q.order_by(date_col.desc()).all()


def get_invoice_by_number(number: str) -> InvoiceRecord | None:
    """Zwróć fakturę po numerze (klucz biznesowy, unique) albo None."""
    with get_session() as session:
        return (
            session.query(InvoiceRecord).filter(InvoiceRecord.number == number).one_or_none()
        )


def mark_sent_ksef(number: str, reference: str, sent_at: datetime | None = None) -> bool:
    """Zapisz na fakturze numer referencyjny KSeF, czas wysyłki i status.

    Zwraca True gdy fakturę znaleziono i zaktualizowano, False gdy nie ma jej
    w rejestrze (np. XML wysłany spoza tego systemu).
    """
    with get_session() as session:
        inv = session.query(InvoiceRecord).filter(InvoiceRecord.number == number).one_or_none()
        if inv is None:
            return False
        inv.status = "sent_ksef"
        inv.ksef_reference = reference
        inv.ksef_sent_at = sent_at or datetime.now()
        session.commit()
    return True


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


def save_expense(record: ExpenseRecord) -> ExpenseRecord:
    with get_session() as session:
        session.merge(record)
        session.commit()
    return record


def get_expenses(month: int | None = None, year: int | None = None) -> list[ExpenseRecord]:
    """Koszty wg miesiaca WPLYWU faktury (receive_date), nie wystawienia."""
    with get_session() as session:
        q = session.query(ExpenseRecord)
        if month and year:
            if month < 12:
                end_date = date(year, month + 1, 1)
            else:
                end_date = date(year + 1, 1, 1)
            q = q.filter(
                ExpenseRecord.receive_date >= date(year, month, 1),
                ExpenseRecord.receive_date < end_date,
            )
        return q.order_by(ExpenseRecord.receive_date.desc()).all()
