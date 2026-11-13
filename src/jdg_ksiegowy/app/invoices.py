"""Przypadki uzycia: faktury sprzedazy — jeden potok wystawiania dla faktur, korekt i kontraktow."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from jdg_ksiegowy.app.audit import audit
from jdg_ksiegowy.app.confirm import require_confirmation, sha256_hex
from jdg_ksiegowy.app.errors import (
    ConfigMissingError,
    ConflictError,
    ExternalServiceError,
    InvalidInputError,
    NotFoundError,
)
from jdg_ksiegowy.config import DATA_DIR, settings
from jdg_ksiegowy.invoice.generator_docx import generate_invoice_docx
from jdg_ksiegowy.invoice.generator_xml import save_invoice_xml
from jdg_ksiegowy.invoice.mailer import send_invoice_email
from jdg_ksiegowy.invoice.models import Buyer, Invoice, InvoiceKind, InvoiceStatus, LineItem
from jdg_ksiegowy.invoice.pdf import PDFConversionError, docx_to_pdf
from jdg_ksiegowy.invoice.whitelist import WhiteListError, lookup
from jdg_ksiegowy.ksef.qr import verification_url
from jdg_ksiegowy.registry.repository import (
    BuyerRepository,
    InvoiceNotFoundError,
    InvoiceRepository,
    PeriodBy,
)

DEFAULT_PAYMENT_DAYS = 14
KSEF_MANDATORY_FROM = date(2026, 4, 1)  # od tego dnia faktura musi miec numer KSeF
CORRECTION_PREFIX = "KOR"


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
    kind: str
    issue_date: date
    sale_date: date
    payment_due: date
    buyer_name: str
    buyer_nip: str
    buyer_country: str
    net: Decimal
    vat: Decimal
    gross: Decimal
    status: str
    ksef_number: str | None
    corrected_number: str | None
    paid_at: datetime | None
    docx_path: str | None
    xml_path: str | None
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def of(cls, inv: Invoice, warnings: list[str] | None = None) -> InvoiceView:
        return cls(
            number=inv.number,
            kind=inv.kind.value,
            issue_date=inv.issue_date,
            sale_date=inv.sale_date,
            payment_due=inv.payment_due,
            buyer_name=inv.buyer.name,
            buyer_nip=inv.buyer.nip or inv.buyer.eu_vat_number or "",
            buyer_country=inv.buyer.country_code,
            net=inv.total_net,
            vat=inv.total_vat,
            gross=inv.total_gross,
            status=inv.status.value,
            ksef_number=inv.ksef_number,
            corrected_number=inv.corrected_number,
            paid_at=inv.paid_at,
            docx_path=inv.docx_path,
            xml_path=inv.xml_path,
            warnings=warnings or [],
        )


class InvoiceList(BaseModel):
    count: int
    total_net: Decimal
    total_vat: Decimal
    total_gross: Decimal
    invoices: list[InvoiceView]


class ItemInput(BaseModel):
    """Pozycja faktury. Stawka albo kod: NP (poza terytorium), ZW, 0, 0_WDT, 0_EXP."""

    description: str
    unit_price_net: Decimal
    quantity: Decimal = Decimal("1")
    unit: str = "usl."
    vat_rate: Decimal | None = None  # None -> stawka sprzedawcy z .env
    vat_code: str | None = None
    gtu: str | None = None

    def to_line(self) -> LineItem:
        return LineItem(
            description=self.description,
            quantity=self.quantity,
            unit=self.unit,
            unit_price_net=self.unit_price_net,
            vat_rate=settings.seller.vat_rate if self.vat_rate is None else self.vat_rate,
            vat_code=self.vat_code,
            gtu=self.gtu,
        )


class IssueInvoiceInput(BaseModel):
    buyer_nip: str = ""  # NIP (PL); dla nabywcy z UE — numer VAT-UE w buyer_eu_vat
    items: list[ItemInput] = Field(default_factory=list)
    net: Decimal | None = None  # skrot: jedna pozycja z `description`
    description: str | None = None
    buyer_name: str | None = None
    buyer_address: str | None = None
    buyer_email: str | None = None
    buyer_country: str = "PL"
    buyer_eu_vat: str | None = None
    issue_date: date | None = None
    sale_date: date | None = None
    payment_due: date | None = None
    period_from: date | None = None
    period_to: date | None = None
    lookup_buyer: bool = True  # nowy nabywca bez nazwy -> Biala lista MF


# --- wspolny potok -----------------------------------------------------------------------


def _documents(invoice: Invoice) -> Invoice:
    """Wizualizacja DOCX (z QR po nadaniu numeru KSeF) i XML FA(3) w data/faktury/RRRR/MM."""
    folder = DATA_DIR / "faktury" / str(invoice.issue_date.year) / f"{invoice.issue_date.month:02d}"
    stem = f"faktura_{invoice.number.replace('/', '_')}"
    xml = save_invoice_xml(invoice, folder / f"{stem}.xml")
    docx = generate_invoice_docx(invoice, folder / f"{stem}.docx")
    return invoice.model_copy(update={"docx_path": str(docx), "xml_path": str(xml)})


def store_new(invoice: Invoice) -> Invoice:
    """Zapisz nowa fakture lub korekte: dokumenty + rejestr + dziennik."""
    stored = _documents(invoice)
    InvoiceRepository().save(stored)
    audit(f"invoice.{invoice.kind.value.lower()}", invoice.number, "ok",
          {"net": str(invoice.total_net), "buyer": invoice.buyer.name})  # fmt: skip
    return stored


def refresh_visualization(invoice: Invoice, env: str) -> Invoice:
    """Po nadaniu numeru KSeF: DOCX z numerem i kodem QR weryfikacji (XML bez zmian)."""
    if not invoice.ksef_number or not invoice.xml_path or not invoice.docx_path:
        return invoice
    url = verification_url(
        settings.seller.nip, invoice.issue_date, Path(invoice.xml_path).read_bytes(), env
    )
    generate_invoice_docx(invoice, Path(invoice.docx_path), qr_url=url)
    return invoice


# --- wystawienie -------------------------------------------------------------------------


def _resolve_buyer(inp: IssueInvoiceInput, warnings: list[str]) -> tuple[Buyer, str | None]:
    known = BuyerRepository().find_by_nip(inp.buyer_nip) if inp.buyer_nip else None
    name = inp.buyer_name or (known.buyer.name if known else None)
    address = inp.buyer_address or (known.buyer.address if known else None)
    if not name and inp.lookup_buyer and inp.buyer_nip and inp.buyer_country == "PL":
        try:
            subject = lookup(inp.buyer_nip, date.today())
        except WhiteListError as e:
            raise ExternalServiceError(str(e), hint="Podaj --buyer-name i --buyer-address.") from e
        if subject is None:
            raise InvalidInputError(
                f"NIP {inp.buyer_nip} nie figuruje w wykazie podatnikow VAT",
                hint="Sprawdz NIP albo podaj --buyer-name i --buyer-address recznie.",
            )
        name, address = subject.name, address or subject.address
        warnings.append(f"Dane nabywcy z Bialej listy MF (status VAT: {subject.vat_status}).")
        if subject.vat_status != "Czynny":
            warnings.append(f"Nabywca nie jest czynnym podatnikiem VAT ({subject.vat_status}).")
    if not name:
        raise InvalidInputError(
            "Brak nazwy nabywcy",
            hint="Podaj --buyer-name i --buyer-address przy pierwszej fakturze dla kontrahenta.",
        )
    buyer = Buyer(
        name=name,
        nip=inp.buyer_nip if inp.buyer_country == "PL" else "",
        address=address or "",
        email=inp.buyer_email or (known.buyer.email if known else None),
        country_code=inp.buyer_country,
        eu_vat_number=inp.buyer_eu_vat,
    )
    return buyer, known.default_description if known else None


def _items(inp: IssueInvoiceInput, default_description: str | None) -> list[LineItem]:
    if inp.items and inp.net is not None:
        raise InvalidInputError("Podaj pozycje (--item) albo --net, nie oba naraz")
    if inp.items:
        return [i.to_line() for i in inp.items]
    if inp.net is None:
        raise InvalidInputError("Brak pozycji faktury", hint="Podaj --net albo --item.")
    description = inp.description or default_description
    if not description:
        raise InvalidInputError(
            "Brak opisu uslugi",
            hint="Podaj --description (zapamietamy go jako domyslny dla kontrahenta).",
        )
    return [ItemInput(description=description, unit_price_net=inp.net).to_line()]


def issue_invoice(inp: IssueInvoiceInput, *, dry_run: bool = False) -> InvoiceView:
    """Wystaw fakture VAT: numer z serii, XML FA(3) + DOCX, wpis w rejestrze."""
    if (inp.period_from is None) != (inp.period_to is None):
        raise InvalidInputError("Okres rozliczeniowy wymaga obu dat: --period-from i --period-to")
    if inp.buyer_country != "PL" and not inp.buyer_eu_vat and not inp.buyer_name:
        raise InvalidInputError("Nabywca zagraniczny wymaga nazwy (i numeru VAT-UE dla firm z UE)")
    warnings: list[str] = []
    buyer, default_description = _resolve_buyer(inp, warnings)
    items = _items(inp, default_description)
    issue = inp.issue_date or date.today()
    invoice = Invoice(
        number=InvoiceRepository().next_number(issue.month, issue.year),
        issue_date=issue,
        sale_date=inp.sale_date or issue,
        period_from=inp.period_from,
        period_to=inp.period_to,
        payment_due=inp.payment_due or issue + timedelta(days=DEFAULT_PAYMENT_DAYS),
        buyer=buyer,
        items=items,
        status=InvoiceStatus.GENERATED,
    )
    if dry_run:
        return InvoiceView.of(invoice, warnings)
    stored = store_new(invoice)
    if buyer.nip and len(items) == 1:
        BuyerRepository().remember_description(buyer.nip, items[0].description)
    return InvoiceView.of(stored, warnings)


def correct_invoice(
    number: str,
    items: list[ItemInput],
    *,
    reason: str,
    issue_date: date | None = None,
    dry_run: bool = False,
) -> InvoiceView:
    """Faktura korygujaca: pozycje roznicowe (ujemne = zmniejszenie) do faktury z rejestru.

    Okres VAT i przychodu: zmniejszenie — data korekty, zwiekszenie — okres faktury pierwotnej.
    """
    original = get_invoice(number)
    if original.kind is InvoiceKind.KOR:
        raise InvalidInputError("Koryguje sie fakture pierwotna, nie korekte", hint=f"{number}")
    if not items:
        raise InvalidInputError("Korekta wymaga pozycji roznicowych (--item)")
    issue = issue_date or date.today()
    lines = [i.to_line() for i in items]
    decrease = sum((li.net_value for li in lines), Decimal("0")) < 0
    correction = Invoice(
        number=InvoiceRepository().next_number(issue.month, issue.year, prefix=CORRECTION_PREFIX),
        kind=InvoiceKind.KOR,
        issue_date=issue,
        sale_date=issue if decrease else original.sale_date,
        payment_due=issue if decrease else issue + timedelta(days=DEFAULT_PAYMENT_DAYS),
        buyer=original.buyer,
        items=lines,
        status=InvoiceStatus.GENERATED,
        corrected_number=original.number,
        corrected_ksef_number=original.ksef_number,
        corrected_issue_date=original.issue_date,
        correction_reason=reason,
    )
    warnings = []
    if original.issue_date >= KSEF_MANDATORY_FROM and not original.ksef_number:
        warnings.append("Faktura korygowana nie ma numeru KSeF — wyslij ja najpierw do KSeF.")
    if dry_run:
        return InvoiceView.of(correction, warnings)
    return InvoiceView.of(store_new(correction), warnings)


# --- odczyt, zaplaty, mail ----------------------------------------------------------------


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
    """Wyslij fakture PDF mailem — czynnosc nieodwracalna, wymaga potwierdzenia.

    Faktura z obowiazkowego okresu KSeF musi miec numer KSeF: wizualizacja przekazywana poza
    KSeF zawiera wtedy numer i kod QR weryfikacji.
    """
    inv = get_invoice(number)
    recipient = to or inv.buyer.email
    if not recipient:
        raise InvalidInputError(f"Brak adresu e-mail kontrahenta faktury {number}", hint="--to")
    if inv.issue_date >= KSEF_MANDATORY_FROM and not inv.ksef_number:
        raise ConflictError(
            f"Faktura {number} nie ma numeru KSeF",
            hint=f"Najpierw `jdg ksef send {number}` — PDF dostanie numer KSeF i kod QR.",
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
            "numer_ksef": inv.ksef_number,
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


class BuyerLookup(BaseModel):
    nip: str
    name: str
    address: str
    vat_status: str
    accounts: list[str]
    known_in_registry: bool


def lookup_buyer(nip: str) -> BuyerLookup:
    """Dane kontrahenta z Bialej listy MF (status VAT, adres, rachunki z wykazu)."""
    try:
        subject = lookup(nip, date.today())
    except WhiteListError as e:
        raise ExternalServiceError(str(e)) from e
    if subject is None:
        raise NotFoundError(f"NIP {nip} nie figuruje w wykazie podatnikow VAT")
    return BuyerLookup(
        nip=subject.nip,
        name=subject.name,
        address=subject.address,
        vat_status=subject.vat_status,
        accounts=subject.accounts,
        known_in_registry=BuyerRepository().find_by_nip(nip) is not None,
    )
