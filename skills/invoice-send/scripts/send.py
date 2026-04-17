#!/usr/bin/env python3
"""Konwertuj DOCX fakture do PDF i wyslij mailem do kontrahenta."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from jdg_ksiegowy.invoice.mailer import send_invoice_email
from jdg_ksiegowy.invoice.pdf import PDFConversionError, docx_to_pdf
from jdg_ksiegowy.registry.db import get_invoices, init_db


def find_invoice(number: str | None, latest: bool):
    init_db()
    if number:
        records = [r for r in get_invoices() if r.number == number]
        if not records:
            return None
        return records[0]
    if latest:
        records = get_invoices()
        return records[0] if records else None
    return None


def main():
    parser = argparse.ArgumentParser(description="Wyslij fakture PDF mailem")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--number", help="Numer faktury np. A1/04/2026")
    group.add_argument("--latest", action="store_true", help="Ostatnio wygenerowana faktura")
    parser.add_argument("--to", required=True, help="Email kontrahenta")
    parser.add_argument("--cc", default=None, help="CC (przecinek-separated)")
    parser.add_argument("--subject", default=None, help="Override subject")
    parser.add_argument("--body", default=None, help="Override body")
    args = parser.parse_args()

    record = find_invoice(args.number, args.latest)
    if record is None:
        print(json.dumps({"success": False, "error": "Faktura nie znaleziona"}, ensure_ascii=False))
        sys.exit(1)

    if not record.docx_path or not Path(record.docx_path).exists():
        print(json.dumps({"success": False, "error": f"Brak pliku DOCX dla {record.number}"}, ensure_ascii=False))
        sys.exit(1)

    try:
        pdf_path = docx_to_pdf(Path(record.docx_path))
    except (FileNotFoundError, PDFConversionError) as e:
        print(json.dumps({"success": False, "error": f"PDF conversion: {e}"}, ensure_ascii=False))
        sys.exit(1)

    result = send_invoice_email(
        to=args.to,
        pdf_path=pdf_path,
        invoice_number=record.number,
        gross_amount=f"{record.total_gross:.2f}",
        payment_due=record.payment_due.isoformat(),
        subject=args.subject,
        body=args.body,
        cc=[e.strip() for e in args.cc.split(",")] if args.cc else None,
    )

    print(json.dumps({
        "success": result.success,
        "to": result.to,
        "subject": result.subject,
        "pdf_path": str(pdf_path),
        "error": result.error,
    }, ensure_ascii=False, indent=2))
    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
