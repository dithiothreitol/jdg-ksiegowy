"""Generator XML FA(3) dla KSeF 2.0 — oparty o ksef2 SDK FA3InvoiceBuilder.

FA(3) obowiazuje od 1.02.2026 (KSeF 2.0). Schemat CRD: wzor/2025/06/25/13775/.
Generacja przez SDK gwarantuje zgodnosc z XSD i semantyka MF.
"""

from __future__ import annotations

from pathlib import Path

from ksef2.fa3 import FA3InvoiceBuilder
from lxml import etree

from jdg_ksiegowy.config import settings
from jdg_ksiegowy.invoice.models import Buyer, Invoice, InvoiceCorrection, LineItem

FA3_NS = "http://crd.gov.pl/wzor/2025/06/25/13775/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

SYSTEM_INFO = "JDG-Ksiegowy/1.0"


def _split_address(address: str) -> tuple[str, str | None]:
    """Rozdziel adres na (AdresL1, AdresL2) po ostatnim przecinku."""
    parts = address.rsplit(", ", 1)
    return (parts[0], parts[1] if len(parts) > 1 else None)


def _vat_rate_for_builder(item: LineItem) -> str:
    """Stawka VAT w formacie akceptowanym przez FA3 builder."""
    if item.vat_code:
        return item.vat_code.lower() if item.vat_code in ("NP", "ZW") else item.vat_code
    return str(int(item.vat_rate))


def _apply_seller(builder: FA3InvoiceBuilder) -> FA3InvoiceBuilder:
    seller = settings.seller
    l1, l2 = _split_address(seller.address)
    return builder.seller(
        name=seller.name,
        country_code="PL",
        address_line_1=l1,
        address_line_2=l2,
        tax_id=seller.nip,
    )


def _apply_buyer(builder: FA3InvoiceBuilder, buyer: Buyer) -> FA3InvoiceBuilder:
    l1, l2 = _split_address(buyer.address)
    kwargs: dict = dict(
        name=buyer.name,
        country_code=buyer.country_code,
        address_line_1=l1,
        address_line_2=l2,
    )
    if buyer.country_code == "PL" and buyer.nip:
        kwargs["tax_id"] = buyer.nip
    elif buyer.eu_vat_number:
        kwargs["eu_vat_id"] = buyer.eu_vat_number
    return builder.buyer(**kwargs)


def _apply_rows(std_body, items: list[LineItem]):
    rows = std_body.rows()
    for item in items:
        rows = rows.add_line(
            name=item.description,
            quantity=item.quantity,
            unit_price_net=item.unit_price_net,
            vat_rate=_vat_rate_for_builder(item),
            unit_of_measure=item.unit,
        )
    return rows.done()


def _apply_payment(std_body, *, due, paid: bool = False):
    seller = settings.seller
    pay = std_body.payment().due_on(due).via("bank_transfer")
    pay = pay.already_paid() if paid else pay.unpaid()
    if seller.bank_account_raw:
        pay = pay.bank_account(
            account_number=seller.bank_account_raw,
            bank_name=seller.bank_name or None,
        )
    return pay.done()


def generate_invoice_xml(invoice: Invoice) -> str:
    """Wygeneruj XML FA(3) dla faktury standardowej."""
    builder = FA3InvoiceBuilder().header(system_info=SYSTEM_INFO)
    builder = _apply_seller(builder)
    builder = _apply_buyer(builder, invoice.buyer)

    std = (
        builder.standard()
        .invoice_number(invoice.number)
        .issue_date(invoice.issue_date)
        .currency("PLN")
    )
    # FA(3): date_of_supply (P_6) i billing_period (OkresFa) sa wzajemnie wykluczajace.
    if invoice.period_from and invoice.period_to:
        std = std.billing_period(
            period_start=invoice.period_from,
            period_end=invoice.period_to,
        )
    else:
        std = std.date_of_supply(invoice.sale_date)
    std = _apply_rows(std, invoice.items)
    std = _apply_payment(std, due=invoice.payment_due, paid=False)
    return std.done().to_xml()


def generate_correction_xml(correction: InvoiceCorrection) -> str:
    """Wygeneruj XML FA(3) korekty (rodzaj KOR)."""
    builder = FA3InvoiceBuilder().header(system_info=SYSTEM_INFO)
    builder = _apply_seller(builder)
    builder = _apply_buyer(builder, correction.buyer)

    cor = (
        builder.correction()
        .invoice_number(correction.number)
        .issue_date(correction.issue_date)
        .date_of_supply(correction.correction_date)
        .currency("PLN")
    )

    reason_text = correction.reason_description or f"Korekta {correction.reason.value}"
    cor_sub = (
        cor.correction()
        .reason(reason_text)
        .add_corrected_invoice(
            issue_date=correction.correction_date,
            invoice_number=correction.original_number,
            ksef_id=correction.original_ksef_reference,
            outside_ksef=correction.original_ksef_reference is None,
        )
    )
    cor = cor_sub.done()

    cor = _apply_rows(cor, correction.items)
    cor = _apply_payment(cor, due=correction.correction_date, paid=False)
    return cor.done().to_xml()


def save_invoice_xml(invoice: Invoice, output_path: Path) -> Path:
    """Wygeneruj i zapisz XML FA(3) do pliku."""
    xml_content = generate_invoice_xml(invoice)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(xml_content, encoding="utf-8")
    return output_path


def save_correction_xml(correction: InvoiceCorrection, output_path: Path) -> Path:
    """Wygeneruj i zapisz XML FA KOR do pliku."""
    xml_content = generate_correction_xml(correction)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(xml_content, encoding="utf-8")
    return output_path


def validate_xml_against_xsd(xml_path: Path, xsd_path: Path) -> tuple[bool, list[str]]:
    """Waliduj XML faktury wobec schematu XSD FA(3).

    Returns:
        (is_valid, list_of_errors)
    """
    try:
        xsd_doc = etree.parse(str(xsd_path))
        schema = etree.XMLSchema(xsd_doc)
        xml_doc = etree.parse(str(xml_path))
        is_valid = schema.validate(xml_doc)
        errors = [str(e) for e in schema.error_log]
        return is_valid, errors
    except etree.XMLSyntaxError as e:
        return False, [f"XML syntax error: {e}"]
