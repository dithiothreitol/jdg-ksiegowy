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
from jdg_ksiegowy.registry.db import InvoiceRecord, get_next_invoice_number, init_db, save_invoice


def parse_period(period_str: str) -> tuple[date, date]:
    """Parse 'DD.MM.YYYY-DD.MM.YYYY' -> (date, date)."""
    parts = period_str.split("-")

    def to_date(s: str) -> date:
        d = s.strip().split(".")
        return date(int(d[2]), int(d[1]), int(d[0]))

    return to_date(parts[0]), to_date(parts[1])


def main():
    parser = argparse.ArgumentParser(description="Generator faktur VAT")
    parser.add_argument("--buyer-name", required=True)
    parser.add_argument("--buyer-nip", required=True)
    parser.add_argument("--buyer-address", default="")
    parser.add_argument("--buyer-email", default="")
    parser.add_argument("--description", default="Konsultacja w zakresie AI i automatyzacji")
    parser.add_argument("--netto", required=True, type=str)
    parser.add_argument("--period", default="", help="DD.MM.YYYY-DD.MM.YYYY")
    args = parser.parse_args()

    init_db()
    seller = settings.seller
    today = date.today()
    netto = Decimal(args.netto)

    number = get_next_invoice_number(today.month, today.year)

    period_from, period_to = None, None
    if args.period:
        period_from, period_to = parse_period(args.period)
    else:
        period_from = date(today.year, today.month, 1)
        period_to = today

    invoice = Invoice(
        number=number,
        issue_date=today,
        sale_date=today,
        period_from=period_from,
        period_to=period_to,
        payment_due=today + timedelta(days=14),
        buyer=Buyer(
            name=args.buyer_name,
            nip=args.buyer_nip,
            address=args.buyer_address,
            email=args.buyer_email or None,
        ),
        items=[
            LineItem(
                description=args.description,
                unit_price_net=netto,
                vat_rate=seller.vat_rate,
            )
        ],
    )

    month_dir = DATA_DIR / "faktury" / str(today.year) / f"{today.month:02d}"
    safe_number = number.replace("/", "_")

    docx_path = generate_invoice_docx(invoice, month_dir / f"faktura_{safe_number}.docx")
    xml_path = save_invoice_xml(invoice, month_dir / f"faktura_{safe_number}.xml")

    record = InvoiceRecord(
        id=invoice.id,
        number=number,
        issue_date=today,
        sale_date=today,
        payment_due=invoice.payment_due,
        buyer_name=args.buyer_name,
        buyer_nip=args.buyer_nip,
        buyer_address=args.buyer_address,
        total_net=invoice.total_net,
        total_vat=invoice.total_vat,
        total_gross=invoice.total_gross,
        vat_rate=seller.vat_rate,
        status="generated",
        docx_path=str(docx_path),
        xml_path=str(xml_path),
    )
    save_invoice(record)

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
