"""Przypadki uzycia: faktury sprzedazy."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel

from jdg_ksiegowy.app.audit import audit
from jdg_ksiegowy.app.confirm import require_confirmation, sha256_hex
from jdg_ksiegowy.app.errors import (
    ConfigMissingError,
    ExternalServiceError,
    InvalidInputError,
    NotFoundError,
)
from jdg_ksiegowy.config import DATA_DIR, settings
from jdg_ksiegowy.invoice.generator_docx import generate_invoice_docx
from jdg_ksiegowy.invoice.generator_xml import save_invoice_xml
from jdg_ksiegowy.invoice.mailer import send_invoice_email
from jdg_ksiegowy.invoice.models import Buyer, Invoice, InvoiceStatus, LineItem
from jdg_ksiegowy.invoice.pdf import PDFConversionError, docx_to_pdf
from jdg_ksiegowy.registry.repository import (
    BuyerRepository,
    InvoiceNotFoundError,
    InvoiceRepository,
    PeriodBy,
)

DEFAULT_PAYMENT_DAYS = 14


class InvoiceView(BaseModel):
    table_columns: ClassVar[tuple[str, ...]] = (
        "number",
        "issue_date",
        "buyer_name",
        "gross",
        "status",
        "ksef_number",
    )

    number: str
    issue_date: date
    sale_date: date
    payment_due: date
    buyer_name: str
    buyer_nip: str
    net: Decimal
    vat: Decimal
    gross: Decimal
    status: str
    ksef_number: str | None
    paid_at: datetime | None
    docx_path: str | None
    xml_path: str | None

    @classmethod
    def of(cls, inv: Invoice) -> InvoiceView:
        return cls(
            number=inv.number,
            issue_date=inv.issue_date,
            sale_date=inv.sale_date,
            payment_due=inv.payment_due,
            buyer_name=inv.buyer.name,
            buyer_nip=inv.buyer.nip,
            net=inv.total_net,
            vat=inv.total_vat,
            gross=inv.total_gross,
            status=inv.status.value,
            ksef_number=inv.ksef_number,
            paid_at=inv.paid_at,
            docx_path=inv.docx_path,
            xml_path=inv.xml_path,
        )


class InvoiceList(BaseModel):
    count: int
    total_net: Decimal
    total_vat: Decimal
    total_gross: Decimal
    invoices: list[InvoiceView]


class IssueInvoiceInput(BaseModel):
    buyer_nip: str
    net: Decimal
    buyer_name: str | None = None
    buyer_address: str | None = None
    buyer_email: str | None = None
    description: str | None = None
    issue_date: date | None = None
    sale_date: date | None = None
    payment_due: date | None = None
    period_from: date | None = None
    period_to: date | None = None


def issue_invoice(inp: IssueInvoiceInput, *, dry_run: bool = False) -> InvoiceView:
    """Wystaw fakture: numer z serii, DOCX + XML FA(3), zapis w rejestrze."""
    invoices, buyers = InvoiceRepository(), BuyerRepository()
    known = buyers.find_by_nip(inp.buyer_nip)
    name = inp.buyer_name or (known.buyer.name if known else None)
    if not name:
        raise InvalidInputError(
            f"NIP {inp.buyer_nip} nie ma w rejestrze kontrahentow",
            hint="Podaj --buyer-name i --buyer-address przy pierwszej fakturze dla kontrahenta.",
        )
    description = inp.description or (known.default_description if known else None)
    if not description:
        raise InvalidInputError(
            "Brak opisu uslugi",
            hint="Podaj --description (zapamietamy go jako domyslny dla kontrahenta).",
        )
    if (inp.period_from is None) != (inp.period_to is None):
        raise InvalidInputError("Okres rozliczeniowy wymaga obu dat: --period-from i --period-to")

    issue = inp.issue_date or date.today()
    number = invoices.next_number(issue.month, issue.year)
    invoice = Invoice(
        number=number,
        issue_date=issue,
        sale_date=inp.sale_date or issue,
        period_from=inp.period_from,
        period_to=inp.period_to,
        payment_due=inp.payment_due or issue + timedelta(days=DEFAULT_PAYMENT_DAYS),
        buyer=Buyer(
            name=name,
            nip=inp.buyer_nip,
            address=inp.buyer_address or (known.buyer.address if known else ""),
            email=inp.buyer_email or (known.buyer.email if known else None),
        ),
        items=[
            LineItem(
                description=description,
                unit_price_net=inp.net,
                vat_rate=settings.seller.vat_rate,
            )
        ],
        status=InvoiceStatus.GENERATED,
    )
    if dry_run:
        return InvoiceView.of(invoice)

    folder = DATA_DIR / "faktury" / str(issue.year) / f"{issue.month:02d}"
    stem = f"faktura_{number.replace('/', '_')}"
    docx = generate_invoice_docx(invoice, folder / f"{stem}.docx")
    xml = save_invoice_xml(invoice, folder / f"{stem}.xml")
    invoice = invoice.model_copy(update={"docx_path": str(docx), "xml_path": str(xml)})
    invoices.save(invoice)
    buyers.remember_description(inp.buyer_nip, description)
    audit("invoice.issue", number, "ok", {"net": str(invoice.total_net), "buyer": name})
    return InvoiceView.of(invoice)


def list_invoices(
    *,
    year: int | None = None,
    month: int | None = None,
    by: PeriodBy = "sale_date",
    unpaid: bool = False,
) -> InvoiceList:
    items = InvoiceRepository().list(year=year, month=month, by=by)
    if unpaid:
        items = [i for i in items if i.paid_at is None]
    return InvoiceList(
        count=len(items),
        total_net=sum((i.total_net for i in items), Decimal("0")),
        total_vat=sum((i.total_vat for i in items), Decimal("0")),
        total_gross=sum((i.total_gross for i in items), Decimal("0")),
        invoices=[InvoiceView.of(i) for i in items],
    )


def get_invoice(number: str) -> Invoice:
    inv = InvoiceRepository().get(number)
    if inv is None:
        raise NotFoundError(
            f"Faktura {number} nie istnieje w rejestrze", hint="Sprawdz `jdg invoice list`."
        )
    return inv


def show_invoice(number: str) -> InvoiceView:
    return InvoiceView.of(get_invoice(number))


def mark_paid(number: str, paid_at: datetime | None = None) -> InvoiceView:
    repo = InvoiceRepository()
    try:
        repo.mark_paid(number, paid_at or datetime.now())
    except InvoiceNotFoundError as e:
        raise NotFoundError(str(e)) from e
    except ValueError as e:
        raise InvalidInputError(str(e)) from e
    audit("invoice.mark_paid", number, "ok", {})
    return show_invoice(number)


class MailResult(BaseModel):
    number: str
    to: str
    subject: str
    pdf_path: str
    status: Literal["sent"]


def mail_invoice(
    number: str,
    *,
    to: str | None = None,
    cc: list[str] | None = None,
    confirm: str | None = None,
) -> MailResult:
    """Wyslij fakture PDF mailem — czynnosc nieodwracalna, wymaga potwierdzenia."""
    inv = get_invoice(number)
    recipient = to or inv.buyer.email
    if not recipient:
        raise InvalidInputError(
            f"Brak adresu e-mail kontrahenta faktury {number}", hint="Podaj --to."
        )
    if not settings.smtp.is_configured():
        raise ConfigMissingError(
            "SMTP nie skonfigurowany", hint="Ustaw SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD w .env."
        )
    if not inv.docx_path or not Path(inv.docx_path).exists():
        raise NotFoundError(f"Brak pliku DOCX faktury {number}")

    require_confirmation(
        action="invoice.mail",
        target=number,
        payload_digest=sha256_hex(Path(inv.docx_path).read_bytes() + recipient.encode()),
        env="smtp",
        summary={
            "faktura": number,
            "do": recipient,
            "kopia": cc or [],
            "brutto": str(inv.total_gross),
            "termin": inv.payment_due.isoformat(),
        },
        confirm=confirm,
    )
    try:
        pdf = docx_to_pdf(Path(inv.docx_path))
    except PDFConversionError as e:
        raise ExternalServiceError(f"Konwersja do PDF nie powiodla sie: {e}") from e
    result = send_invoice_email(
        to=recipient,
        pdf_path=pdf,
        invoice_number=number,
        gross_amount=f"{inv.total_gross:.2f}",
        payment_due=inv.payment_due.isoformat(),
        cc=cc,
    )
    if not result.success:
        audit("invoice.mail", number, "error", {"to": recipient, "error": result.error})
        raise ExternalServiceError(f"Wysylka e-mail nie powiodla sie: {result.error}")
    audit("invoice.mail", number, "ok", {"to": recipient})
    return MailResult(
        number=number, to=recipient, subject=result.subject, pdf_path=str(pdf), status="sent"
    )
