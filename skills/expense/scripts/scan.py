#!/usr/bin/env python3
"""OCR faktury zakupu (PDF/JPG/PNG) — wyciagniecie danych do akceptacji.

Uzycie:
    python3 scan.py --file faktura.pdf
    python3 scan.py --file faktura.jpg --save

Bez --save pokazuje wynik do akceptacji; z --save zapisuje do SQLite.
"""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from jdg_ksiegowy.expenses.ocr import OCRError, build_default_ocr
from jdg_ksiegowy.registry.db import ExpenseRecord, init_db, save_expense


def main():
    parser = argparse.ArgumentParser(description="OCR faktury zakupu")
    parser.add_argument("--file", required=True, help="Sciezka do PDF/JPG/PNG")
    parser.add_argument(
        "--save",
        action="store_true",
        help="Zapisz wynik do rejestru bez potwierdzenia (inaczej tylko preview)",
    )
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(json.dumps({"success": False, "error": f"Plik nie istnieje: {file_path}"}))
        sys.exit(1)

    ocr = build_default_ocr()
    try:
        extracted = ocr.extract(file_path)
    except OCRError as e:
        print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)

    preview = {
        "seller_name": extracted.seller_name,
        "seller_nip": extracted.seller_nip,
        "seller_country": extracted.seller_country,
        "document_number": extracted.document_number,
        "issue_date": extracted.issue_date.isoformat(),
        "description": extracted.description,
        "category": extracted.category.value,
        "total_net": str(extracted.total_net),
        "total_vat": str(extracted.total_vat),
        "vat_rate": str(extracted.vat_rate),
        "source": extracted.source,
    }

    if not args.save:
        print(
            json.dumps(
                {"success": True, "preview": preview, "saved": False}, ensure_ascii=False, indent=2
            )
        )
        return

    init_db()
    brutto = extracted.total_net + extracted.total_vat
    record = ExpenseRecord(
        id=f"{extracted.seller_nip}-{extracted.document_number}",
        seller_name=extracted.seller_name,
        seller_nip=extracted.seller_nip,
        seller_country=extracted.seller_country,
        document_number=extracted.document_number,
        issue_date=extracted.issue_date,
        receive_date=extracted.issue_date,
        description=extracted.description,
        category=extracted.category.value,
        total_net=extracted.total_net,
        total_vat=extracted.total_vat,
        total_gross=brutto,
        vat_rate=extracted.vat_rate,
        vat_deduction_pct=Decimal("100"),
        file_path=str(file_path.resolve()),
    )
    save_expense(record)
    print(
        json.dumps(
            {"success": True, "preview": preview, "saved": True, "id": record.id},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
