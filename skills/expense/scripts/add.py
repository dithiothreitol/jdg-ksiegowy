#!/usr/bin/env python3
"""Dodaj fakture zakupu (koszt) do rejestru SQLite."""

import argparse
import json
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from jdg_ksiegowy.expenses.models import ExpenseCategory
from jdg_ksiegowy.registry.db import ExpenseRecord, init_db, save_expense


def parse_iso_date(s: str) -> date:
    return date.fromisoformat(s)


def main():
    parser = argparse.ArgumentParser(description="Dodaj fakture zakupu do rejestru")
    parser.add_argument("--seller-name", required=True, help="Nazwa sprzedawcy")
    parser.add_argument("--seller-nip", required=True, help="NIP sprzedawcy")
    parser.add_argument("--seller-country", default="PL")
    parser.add_argument("--document-number", required=True, help="Numer faktury sprzedawcy")
    parser.add_argument("--issue-date", required=True, help="Data wystawienia (YYYY-MM-DD)")
    parser.add_argument(
        "--receive-date",
        default=None,
        help="Data wplywu (YYYY-MM-DD). Domyslnie: data wystawienia.",
    )
    parser.add_argument("--description", default="")
    parser.add_argument(
        "--category",
        default=ExpenseCategory.INNE.value,
        choices=[c.value for c in ExpenseCategory],
    )
    parser.add_argument("--netto", required=True, help="Kwota netto")
    parser.add_argument("--vat", required=True, help="Kwota VAT")
    parser.add_argument("--vat-rate", default="23", help="Stawka VAT (procent)")
    parser.add_argument(
        "--no-vat-deductible",
        action="store_true",
        help="VAT NIE podlega odliczeniu (np. paliwo do auta osobowego, reprezentacja)",
    )
    parser.add_argument("--file-path", default=None, help="Sciezka do PDF/JPG dowodu")
    parser.add_argument("--notes", default=None)
    args = parser.parse_args()

    init_db()
    issue = parse_iso_date(args.issue_date)
    receive = parse_iso_date(args.receive_date) if args.receive_date else issue

    netto = Decimal(args.netto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    vat = Decimal(args.vat).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    brutto = (netto + vat).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    record = ExpenseRecord(
        id=f"{args.seller_nip}-{args.document_number}",
        seller_name=args.seller_name,
        seller_nip=args.seller_nip,
        seller_country=args.seller_country,
        document_number=args.document_number,
        issue_date=issue,
        receive_date=receive,
        description=args.description,
        category=args.category,
        total_net=netto,
        total_vat=vat,
        total_gross=brutto,
        vat_rate=Decimal(args.vat_rate),
        vat_deductible=not args.no_vat_deductible,
        file_path=args.file_path,
        notes=args.notes,
    )
    save_expense(record)

    result = {
        "id": record.id,
        "seller": args.seller_name,
        "document_number": args.document_number,
        "issue_date": issue.isoformat(),
        "receive_date": receive.isoformat(),
        "netto": str(netto),
        "vat": str(vat),
        "brutto": str(brutto),
        "vat_deductible": not args.no_vat_deductible,
        "category": args.category,
        "status": "saved",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
