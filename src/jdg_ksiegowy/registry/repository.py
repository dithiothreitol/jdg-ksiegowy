"""Repozytoria: jedyne miejsce mapowania rekordow ORM <-> modele domenowe.

Reszta kodu (JPK, PIT-28, dashboard, CLI) operuje na `Invoice` / `Expense` /
`Contract` i nie zna SQLAlchemy.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from jdg_ksiegowy.expenses.models import Expense, ExpenseCategory
from jdg_ksiegowy.invoice.models import (
    Buyer,
    Contract,
    Invoice,
    InvoiceKind,
    InvoiceStatus,
    LineItem,
)
from jdg_ksiegowy.registry.db import (
    BuyerRecord,
    ContractRecord,
    ExpenseRecord,
    FilingRecord,
    InvoiceItemRecord,
    InvoiceRecord,
    TaxPaymentRecord,
    get_session,
    init_db,
)
from jdg_ksiegowy.tax.income import income_date
from jdg_ksiegowy.validators import check_ksef_number

SessionFactory = Callable[[], Session]
PeriodBy = Literal["sale_date", "issue_date", "income"]


def _month_range(year: int, month: int) -> tuple[date, date]:
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return date(year, month, 1), end


def _in_period(d: date, year: int, month: int | None) -> bool:
    return d.year == year and (month is None or d.month == month)


class InvoiceNotFoundError(LookupError):
    """Faktury o podanym numerze nie ma w rejestrze."""


# --- Faktury sprzedazy ---------------------------------------------------------


def _invoice_to_domain(r: InvoiceRecord) -> Invoice:
    return Invoice(
        id=r.id,
        number=r.number,
        kind=InvoiceKind(r.kind),
        issue_date=r.issue_date,
        sale_date=r.sale_date,
        period_from=r.period_from,
        period_to=r.period_to,
        payment_due=r.payment_due,
        buyer=Buyer(
            name=r.buyer_name,
            nip=r.buyer_nip,
            address=r.buyer_address or "",
            email=r.buyer_email,
            country_code=r.buyer_country,
            eu_vat_number=r.buyer_eu_vat,
        ),
        items=[
            LineItem(
                description=i.description,
                quantity=i.quantity,
                unit=i.unit,
                unit_price_net=i.unit_price_net,
                vat_rate=i.vat_rate,
                vat_code=i.vat_code,
                gtu=i.gtu,
            )
            for i in r.items
        ],
        status=InvoiceStatus(r.status or InvoiceStatus.GENERATED),
        ksef_number=r.ksef_number,
        ksef_reference=r.ksef_reference,
        ksef_sent_at=r.ksef_sent_at,
        ksef_acquired_at=r.ksef_acquired_at,
        paid_at=r.paid_at,
        docx_path=r.docx_path,
        xml_path=r.xml_path,
        notes=r.notes,
        corrected_number=r.corrected_number,
        corrected_ksef_number=r.corrected_ksef_number,
        corrected_issue_date=r.corrected_issue_date,
        correction_reason=r.correction_reason,
    )


def _apply_invoice(r: InvoiceRecord, inv: Invoice) -> None:
    r.number = inv.number
    r.kind = inv.kind.value
    r.issue_date = inv.issue_date
    r.sale_date = inv.sale_date
    r.period_from = inv.period_from
    r.period_to = inv.period_to
    r.payment_due = inv.payment_due
    r.buyer_name = inv.buyer.name
    r.buyer_nip = inv.buyer.nip
    r.buyer_address = inv.buyer.address
    r.buyer_email = inv.buyer.email
    r.buyer_country = inv.buyer.country_code
    r.buyer_eu_vat = inv.buyer.eu_vat_number
    r.total_net = inv.total_net
    r.total_vat = inv.total_vat
    r.total_gross = inv.total_gross
    r.status = inv.status.value
    r.ksef_number = inv.ksef_number
    r.ksef_reference = inv.ksef_reference
    r.ksef_sent_at = inv.ksef_sent_at
    r.ksef_acquired_at = inv.ksef_acquired_at
    r.paid_at = inv.paid_at
    r.docx_path = inv.docx_path
    r.xml_path = inv.xml_path
    r.notes = inv.notes
    r.corrected_number = inv.corrected_number
    r.corrected_ksef_number = inv.corrected_ksef_number
    r.corrected_issue_date = inv.corrected_issue_date
    r.correction_reason = inv.correction_reason
    r.items = [
        InvoiceItemRecord(
            position=pos,
            description=item.description,
            quantity=item.quantity,
            unit=item.unit,
            unit_price_net=item.unit_price_net,
            vat_rate=item.vat_rate,
            vat_code=item.vat_code,
            gtu=item.gtu,
            net=item.net_value,
            vat=item.vat_amount,
            gross=item.gross_value,
        )
        for pos, item in enumerate(inv.items, start=1)
    ]


class InvoiceRepository:
    def __init__(self, session_factory: SessionFactory = get_session):
        init_db()
        self._session = session_factory

    def save(self, invoice: Invoice) -> None:
        """Zapisz (wstaw albo nadpisz) fakture z pozycjami i zapamietaj kontrahenta."""
        with self._session() as s:
            record = s.get(InvoiceRecord, invoice.id) or InvoiceRecord(id=invoice.id)
            _apply_invoice(record, invoice)
            s.add(record)
            if invoice.buyer.nip:
                _touch_buyer(s, invoice.buyer, default_vat_rate=_first_rate(invoice))
            s.commit()

    def get(self, number: str) -> Invoice | None:
        with self._session() as s:
            r = s.scalar(select(InvoiceRecord).where(InvoiceRecord.number == number))
            return _invoice_to_domain(r) if r else None

    def list(
        self,
        *,
        year: int | None = None,
        month: int | None = None,
        by: PeriodBy = "sale_date",
    ) -> list[Invoice]:
        """Faktury z okresu wg wybranej daty, najnowsze pierwsze.

        - `sale_date`: moment obowiazku VAT (art. 19a) — okres JPK_V7M,
        - `issue_date`: data wystawienia,
        - `income`: data uzyskania przychodu (art. 14 ust. 1c) — PIT-28, JPK_EWP.
        """
        with self._session() as s:
            q = select(InvoiceRecord)
            if year is not None and by != "income":
                column = InvoiceRecord.sale_date if by == "sale_date" else InvoiceRecord.issue_date
                start, end = (
                    _month_range(year, month) if month else (date(year, 1, 1), date(year + 1, 1, 1))
                )
                q = q.where(column >= start, column < end)
            invoices = [_invoice_to_domain(r) for r in s.scalars(q)]
        if year is not None and by == "income":
            invoices = [i for i in invoices if _in_period(income_date(i), year, month)]
        key = {
            "sale_date": lambda i: i.sale_date,
            "issue_date": lambda i: i.issue_date,
            "income": income_date,
        }[by]
        return sorted(invoices, key=key, reverse=True)

    def previous_for_buyer(self, invoice: Invoice) -> Invoice | None:
        """Ostatnia wczesniejsza faktura VAT tego samego nabywcy (po NIP, bez NIP po nazwie)."""
        buyer = (
            InvoiceRecord.buyer_nip == invoice.buyer.nip
            if invoice.buyer.nip
            else InvoiceRecord.buyer_name == invoice.buyer.name
        )
        with self._session() as s:
            r = s.scalars(
                select(InvoiceRecord)
                .where(
                    buyer,
                    InvoiceRecord.kind == InvoiceKind.VAT.value,
                    InvoiceRecord.number != invoice.number,
                    InvoiceRecord.issue_date <= invoice.issue_date,
                )
                .order_by(InvoiceRecord.issue_date.desc(), InvoiceRecord.created_at.desc())
                .limit(1)
            ).first()
            return _invoice_to_domain(r) if r else None

    def next_number(self, month: int, year: int, prefix: str = "A") -> str:
        """Kolejny numer w serii: {prefix}{n}/MM/RRRR."""
        with self._session() as s:
            taken = s.scalars(
                select(InvoiceRecord.number).where(
                    InvoiceRecord.number.like(f"{prefix}%/{month:02d}/{year}")
                )
            ).all()
        heads = (n[len(prefix) :].split("/")[0] for n in taken)
        seqs = [int(h) for h in heads if h.isdigit()]
        return f"{prefix}{max(seqs, default=0) + 1}/{month:02d}/{year}"

    def mark_sent_ksef(
        self,
        number: str,
        *,
        reference: str,
        ksef_number: str | None,
        acquired_at: datetime | None = None,
        upo_path: str | None = None,
        sent_at: datetime | None = None,
    ) -> None:
        with self._session() as s:
            r = self._require(s, number)
            r.status = InvoiceStatus.SENT_KSEF.value if r.paid_at is None else r.status
            r.ksef_reference = reference
            r.ksef_number = ksef_number
            r.ksef_acquired_at = acquired_at
            r.ksef_upo_path = upo_path
            r.ksef_sent_at = sent_at or datetime.now()
            s.commit()

    def set_ksef_number(self, number: str, ksef_number: str, acquired_at: datetime | None) -> None:
        """Uzupelnij numer KSeF faktury wyslanej wczesniej (backfill)."""
        check_ksef_number(ksef_number)
        with self._session() as s:
            r = self._require(s, number)
            r.ksef_number = ksef_number
            r.ksef_acquired_at = acquired_at
            s.commit()

    def mark_paid(self, number: str, paid_at: datetime) -> None:
        with self._session() as s:
            r = self._require(s, number)
            if r.paid_at is not None:
                raise ValueError(f"Faktura {number!r} jest już zapłacona ({r.paid_at:%Y-%m-%d})")
            r.paid_at = paid_at
            r.status = InvoiceStatus.PAID.value
            s.commit()

    @staticmethod
    def _require(s: Session, number: str) -> InvoiceRecord:
        r = s.scalar(select(InvoiceRecord).where(InvoiceRecord.number == number))
        if r is None:
            raise InvoiceNotFoundError(f"Faktura {number!r} nie istnieje w rejestrze")
        return r


def _first_rate(inv: Invoice) -> Decimal | None:
    return inv.items[0].vat_rate if inv.items else None


# --- Kontrahenci ---------------------------------------------------------------


@dataclass(frozen=True)
class KnownBuyer:
    """Kontrahent z rejestru — dane do podpowiedzi przy kolejnej fakturze."""

    buyer: Buyer
    default_description: str | None


def _touch_buyer(s: Session, buyer: Buyer, default_vat_rate: Decimal | None) -> None:
    existing = s.scalar(select(BuyerRecord).where(BuyerRecord.nip == buyer.nip))
    now = datetime.now()
    if existing is None:
        s.add(
            BuyerRecord(
                id=str(uuid.uuid4()),
                name=buyer.name,
                nip=buyer.nip,
                eu_vat_number=buyer.eu_vat_number,
                address=buyer.address,
                email=buyer.email,
                country_code=buyer.country_code,
                default_vat_rate=default_vat_rate,
                created_at=now,
                last_used_at=now,
            )
        )
        return
    existing.name = buyer.name
    existing.address = buyer.address or existing.address
    existing.email = buyer.email or existing.email
    existing.last_used_at = now


class BuyerRepository:
    def __init__(self, session_factory: SessionFactory = get_session):
        init_db()
        self._session = session_factory

    def find_by_nip(self, nip: str) -> KnownBuyer | None:
        if not nip:
            return None
        with self._session() as s:
            r = s.scalar(select(BuyerRecord).where(BuyerRecord.nip == nip))
            return self._to_known(r) if r else None

    def find_by_name(self, name: str) -> KnownBuyer | None:
        if not name:
            return None
        with self._session() as s:
            r = s.scalar(
                select(BuyerRecord)
                .where(BuyerRecord.name.ilike(f"%{name}%"))
                .order_by(BuyerRecord.last_used_at.desc())
            )
            return self._to_known(r) if r else None

    def remember_description(self, nip: str, description: str) -> None:
        """Zapamietaj opis uslugi jako domyslny, jesli kontrahent go jeszcze nie ma."""
        with self._session() as s:
            r = s.scalar(select(BuyerRecord).where(BuyerRecord.nip == nip))
            if r is not None and not r.default_description:
                r.default_description = description
                s.commit()

    @staticmethod
    def _to_known(r: BuyerRecord) -> KnownBuyer:
        return KnownBuyer(
            buyer=Buyer(
                name=r.name,
                nip=r.nip or "",
                address=r.address or "",
                email=r.email,
                country_code=r.country_code or "PL",
                eu_vat_number=r.eu_vat_number,
            ),
            default_description=r.default_description,
        )


# --- Koszty --------------------------------------------------------------------


def _expense_to_domain(r: ExpenseRecord) -> Expense:
    return Expense(
        id=r.id,
        seller_name=r.seller_name,
        seller_nip=r.seller_nip,
        seller_country=r.seller_country or "PL",
        document_number=r.document_number,
        issue_date=r.issue_date,
        receive_date=r.receive_date,
        description=r.description or "",
        category=ExpenseCategory(r.category) if r.category else ExpenseCategory.INNE,
        total_net=r.total_net,
        total_vat=r.total_vat,
        vat_rate=r.vat_rate if r.vat_rate is not None else Decimal("23"),
        vat_deduction_pct=r.vat_deduction_pct,
        reverse_charge=r.reverse_charge,
        file_path=r.file_path,
        notes=r.notes,
        ksef_number=r.ksef_number,
    )


class ExpenseRepository:
    def __init__(self, session_factory: SessionFactory = get_session):
        init_db()
        self._session = session_factory

    def save(self, expense: Expense) -> None:
        with self._session() as s:
            r = s.get(ExpenseRecord, expense.id) or ExpenseRecord(id=expense.id)
            r.seller_name = expense.seller_name
            r.seller_nip = expense.seller_nip
            r.seller_country = expense.seller_country
            r.document_number = expense.document_number
            r.issue_date = expense.issue_date
            r.receive_date = expense.receive_date
            r.description = expense.description
            r.category = expense.category.value
            r.total_net = expense.total_net
            r.total_vat = expense.total_vat
            r.total_gross = expense.total_gross
            r.vat_rate = expense.vat_rate
            r.vat_deduction_pct = expense.vat_deduction_pct
            r.reverse_charge = expense.reverse_charge
            r.file_path = expense.file_path
            r.notes = expense.notes
            r.ksef_number = expense.ksef_number
            s.add(r)
            s.commit()

    def list(self, *, year: int | None = None, month: int | None = None) -> list[Expense]:
        """Koszty wg miesiaca WPLYWU (receive_date) — on decyduje o okresie odliczenia."""
        with self._session() as s:
            q = select(ExpenseRecord)
            if year is not None:
                start, end = (
                    _month_range(year, month) if month else (date(year, 1, 1), date(year + 1, 1, 1))
                )
                q = q.where(ExpenseRecord.receive_date >= start, ExpenseRecord.receive_date < end)
            q = q.order_by(ExpenseRecord.receive_date.desc())
            return [_expense_to_domain(r) for r in s.scalars(q)]

    def known_keys(self) -> tuple[set[str], set[str]]:
        """(id, numery KSeF) juz zapisanych kosztow — do deduplikacji importu."""
        with self._session() as s:
            rows = s.execute(select(ExpenseRecord.id, ExpenseRecord.ksef_number)).all()
        return {r.id for r in rows}, {r.ksef_number for r in rows if r.ksef_number}


# --- Kontrakty cykliczne -------------------------------------------------------


class ContractRepository:
    def __init__(self, session_factory: SessionFactory = get_session):
        init_db()
        self._session = session_factory

    def save(self, contract: Contract) -> None:
        with self._session() as s:
            r = s.get(ContractRecord, contract.id) or ContractRecord(id=contract.id)
            r.buyer_name = contract.buyer.name
            r.buyer_nip = contract.buyer.nip
            r.buyer_address = contract.buyer.address
            r.buyer_email = contract.buyer.email
            r.description = contract.description
            r.net_amount = contract.net_amount
            r.vat_rate = contract.vat_rate
            r.cycle = contract.cycle
            r.day_of_month = contract.day_of_month
            r.auto_send_ksef = contract.auto_send_ksef
            r.auto_send_email = contract.auto_send_email
            r.active = contract.active
            r.created_at = contract.created_at
            s.add(r)
            s.commit()

    def active(self) -> list[Contract]:
        with self._session() as s:
            rows = s.scalars(select(ContractRecord).where(ContractRecord.active.is_(True)))
            return [
                Contract(
                    id=r.id,
                    buyer=Buyer(
                        name=r.buyer_name,
                        nip=r.buyer_nip,
                        address=r.buyer_address or "",
                        email=r.buyer_email,
                    ),
                    description=r.description,
                    net_amount=r.net_amount,
                    vat_rate=r.vat_rate if r.vat_rate is not None else Decimal("23"),
                    cycle=r.cycle or "monthly",
                    day_of_month=r.day_of_month if r.day_of_month is not None else -1,
                    auto_send_ksef=bool(r.auto_send_ksef),
                    auto_send_email=bool(r.auto_send_email),
                    active=True,
                    created_at=r.created_at or datetime.now(),
                )
                for r in rows
            ]


# --- Zlozone deklaracje (filings) ---------------------------------------------


@dataclass(frozen=True)
class Filing:
    id: int
    form: str
    year: int
    month: int | None
    purpose: int
    file_path: str
    sha256: str
    env: str
    status: str
    reference_number: str | None
    status_code: int | None
    upo_path: str | None
    error: str | None
    created_at: datetime
    submitted_at: datetime | None
    updated_at: datetime | None


def _filing(r: FilingRecord) -> Filing:
    return Filing(
        id=r.id,
        form=r.form,
        year=r.year,
        month=r.month,
        purpose=r.purpose,
        file_path=r.file_path,
        sha256=r.sha256,
        env=r.env,
        status=r.status,
        reference_number=r.reference_number,
        status_code=r.status_code,
        upo_path=r.upo_path,
        error=r.error,
        created_at=r.created_at,
        submitted_at=r.submitted_at,
        updated_at=r.updated_at,
    )


class FilingRepository:
    def __init__(self, session_factory: SessionFactory = get_session):
        init_db()
        self._session = session_factory

    def create(
        self,
        *,
        form: str,
        year: int,
        month: int | None,
        purpose: int,
        file_path: str,
        sha256: str,
        env: str,
    ) -> Filing:
        now = datetime.now()
        with self._session() as s:
            r = FilingRecord(
                form=form,
                year=year,
                month=month,
                purpose=purpose,
                file_path=file_path,
                sha256=sha256,
                env=env,
                status="submitting",
                created_at=now,
                submitted_at=now,
            )
            s.add(r)
            s.commit()
            return _filing(r)

    def update(self, filing_id: int, **fields: object) -> Filing:
        with self._session() as s:
            r = s.get(FilingRecord, filing_id)
            if r is None:
                raise LookupError(f"Brak deklaracji id={filing_id}")
            for name, value in fields.items():
                setattr(r, name, value)
            r.updated_at = datetime.now()
            s.commit()
            return _filing(r)

    def get_by_reference(self, reference: str) -> Filing | None:
        with self._session() as s:
            r = s.scalar(select(FilingRecord).where(FilingRecord.reference_number == reference))
            return _filing(r) if r else None

    def list(
        self, *, form: str | None = None, year: int | None = None, month: int | None = None
    ) -> list[Filing]:
        with self._session() as s:
            q = select(FilingRecord)
            if form:
                q = q.where(FilingRecord.form == form)
            if year is not None:
                q = q.where(FilingRecord.year == year)
            if month is not None:
                q = q.where(FilingRecord.month == month)
            return [_filing(r) for r in s.scalars(q.order_by(FilingRecord.id.desc()))]


# --- Zaplaty podatkow i skladek ---------------------------------------------------

PaymentType = Literal["ryczalt", "vat", "zus_health", "zus_social"]


@dataclass(frozen=True)
class TaxPayment:
    type: PaymentType
    year: int
    month: int
    amount: Decimal
    due_date: date
    paid_at: datetime | None


class TaxPaymentRepository:
    def __init__(self, session_factory: SessionFactory = get_session):
        init_db()
        self._session = session_factory

    def record(self, payment: TaxPayment) -> None:
        """Zapisz zaplate za okres (nadpisuje wczesniejszy wpis tego samego typu i okresu)."""
        with self._session() as s:
            r = s.scalar(
                select(TaxPaymentRecord).where(
                    TaxPaymentRecord.type == payment.type,
                    TaxPaymentRecord.year == payment.year,
                    TaxPaymentRecord.month == payment.month,
                )
            ) or TaxPaymentRecord(type=payment.type, year=payment.year, month=payment.month)
            r.amount = payment.amount
            r.due_date = payment.due_date
            r.paid = payment.paid_at is not None
            r.paid_at = payment.paid_at
            s.add(r)
            s.commit()

    def list(self, *, year: int | None = None) -> list[TaxPayment]:
        with self._session() as s:
            q = select(TaxPaymentRecord)
            if year is not None:
                q = q.where(TaxPaymentRecord.year == year)
            rows = s.scalars(q.order_by(TaxPaymentRecord.year, TaxPaymentRecord.month))
            return [
                TaxPayment(
                    type=r.type,  # type: ignore[arg-type]
                    year=r.year,
                    month=r.month,
                    amount=r.amount,
                    due_date=r.due_date,
                    paid_at=r.paid_at if r.paid else None,
                )
                for r in rows
            ]
