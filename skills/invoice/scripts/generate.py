#!/usr/bin/env python3
"""Generator faktur DOCX + XML FA(3) — AgentSkill dla OpenClaw."""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

# Dodaj src/ do PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from decimal import Decimal

from jdg_ksiegowy.config import DATA_DIR, settings
from jdg_ksiegowy.invoice.generator_docx import generate_invoice_docx
from jdg_ksiegowy.invoice.generator_xml import save_invoice_xml
from jdg_ksiegowy.invoice.models import Buyer, Invoice, LineItem
from jdg_ksiegowy.registry.db import (
    BuyerRecord,
    InvoiceRecord,
    find_buyer_by_nip,
    get_next_invoice_number,
    init_db,
    save_buyer,
    save_invoice,
)


def parse_period(period_str: str) -> tuple[date, date]:
    """Parse 'DD.MM.YYYY-DD.MM.YYYY' -> (date, date)."""
    parts = period_str.split("-")

    def to_date(s: str) -> date:
        d = s.strip().split(".")
        return date(int(d[2]), int(d[1]), int(d[0]))

    return to_date(parts[0]), to_date(parts[1])


def main():
    parser = argparse.ArgumentParser(description="Generator faktur VAT")
    parser.add_argument("--buyer-name", default="")
    parser.add_argument("--buyer-nip", required=True)
    parser.add_argument("--buyer-address", default="")
    parser.add_argument("--buyer-email", default="")
    parser.add_argument("--description", default="")
    parser.add_argument("--netto", required=True, type=str)
    parser.add_argument("--period", default="", help="DD.MM.YYYY-DD.MM.YYYY")
    parser.add_argument(
        "--issue-date", default="", help="YYYY-MM-DD (domyślnie: dziś)"
    )
    parser.add_argument(
        "--sale-date",
        default="",
        help="YYYY-MM-DD — data sprzedaży/wykonania usługi (decyduje o miesiącu JPK)",
    )
    parser.add_argument(
        "--payment-due", default="", help="YYYY-MM-DD (domyślnie: issue-date + 14 dni)"
    )
    args = parser.parse_args()

    init_db()
    seller = settings.seller

    issue_date = date.fromisoformat(args.issue_date) if args.issue_date else date.today()
    sale_date = date.fromisoformat(args.sale_date) if args.sale_date else issue_date
    payment_due = (
        date.fromisoformat(args.payment_due)
        if args.payment_due
        else issue_date + timedelta(days=14)
    )

    netto = Decimal(args.netto)

    # Reuse zapamiętanego kontrahenta po NIP — jeśli istnieje, uzupełniamy
    # brakujące pola z rejestru zamiast wymagać przepisywania danych.
    cached = find_buyer_by_nip(args.buyer_nip)
    buyer_name = args.buyer_name or (cached.name if cached else "")
    buyer_address = args.buyer_address or (cached.address if cached else "")
    buyer_email = args.buyer_email or (cached.email if cached else "") or None
    description = (
        args.description
        or (cached.default_description if cached else "")
        or "Konsultacja w zakresie AI i automatyzacji"
    )
    if not buyer_name:
        raise SystemExit(
            f"NIP {args.buyer_nip} nie ma w rejestrze kontrahentów — podaj --buyer-name"
        )

    number = get_next_invoice_number(issue_date.month, issue_date.year)

    period_from, period_to = None, None
    if args.period:
        period_from, period_to = parse_period(args.period)

    invoice = Invoice(
        number=number,
        issue_date=issue_date,
        sale_date=sale_date,
        period_from=period_from,
        period_to=period_to,
        payment_due=payment_due,
        buyer=Buyer(
            name=buyer_name,
            nip=args.buyer_nip,
            address=buyer_address,
            email=buyer_email,
        ),
        items=[
            LineItem(
                description=description,
                unit_price_net=netto,
                vat_rate=seller.vat_rate,
            )
        ],
    )

    month_dir = DATA_DIR / "faktury" / str(issue_date.year) / f"{issue_date.month:02d}"
    safe_number = number.replace("/", "_")

    docx_path = generate_invoice_docx(invoice, month_dir / f"faktura_{safe_number}.docx")
    xml_path = save_invoice_xml(invoice, month_dir / f"faktura_{safe_number}.xml")

    record = InvoiceRecord(
        id=invoice.id,
        number=number,
        issue_date=issue_date,
        sale_date=sale_date,
        payment_due=payment_due,
        buyer_name=buyer_name,
        buyer_nip=args.buyer_nip,
        buyer_address=buyer_address,
        total_net=invoice.total_net,
        total_vat=invoice.total_vat,
        total_gross=invoice.total_gross,
        vat_rate=seller.vat_rate,
        status="generated",
        docx_path=str(docx_path),
        xml_path=str(xml_path),
    )
    save_invoice(record)

    # Dograj do rejestru kontrahentów email i typowy opis (InvoiceRecord ich nie nosi)
    if buyer_email or description:
        existing = find_buyer_by_nip(args.buyer_nip)
        if existing is not None:
            if buyer_email:
                existing.email = buyer_email
            if description and not existing.default_description:
                existing.default_description = description
            save_buyer(existing)

    result = {
        "number": number,
        "netto": str(invoice.total_net),
        "vat": str(invoice.total_vat),
        "brutto": str(invoice.total_gross),
        "docx_path": str(docx_path),
        "xml_path": str(xml_path),
        "payment_due": invoice.payment_due.isoformat(),
        "status": "generated",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
