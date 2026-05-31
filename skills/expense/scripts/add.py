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
    parser.add_argument(
        "--vat",
        default=None,
        help="Kwota VAT. Przy --reverse-charge opcjonalna (liczona z netto*stawka).",
    )
    parser.add_argument("--vat-rate", default="23", help="Stawka VAT (procent)")
    parser.add_argument(
        "--reverse-charge",
        action="store_true",
        help=(
            "Import usług / odwrotne obciążenie (faktura zagraniczna bez VAT). "
            "Nabywca sam nalicza VAT należny i odlicza go (netto efekt 0). "
            "Ustaw --seller-country (UE -> K_29/K_30, spoza UE -> K_27/K_28)."
        ),
    )
    parser.add_argument(
        "--vat-deduction-pct",
        default="100",
        help=(
            "Procent VAT odliczalnego (0-100). Default 100. "
            "50 = auto osobowe mieszane / prywatne sluzbowo. "
            "0 = brak odliczenia (reprezentacja)."
        ),
    )
    parser.add_argument("--file-path", default=None, help="Sciezka do PDF/JPG dowodu")
    parser.add_argument("--notes", default=None)
    args = parser.parse_args()

    init_db()
    issue = parse_iso_date(args.issue_date)
    receive = parse_iso_date(args.receive_date) if args.receive_date else issue

    netto = Decimal(args.netto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    vat_rate = Decimal(args.vat_rate)
    if args.vat is not None:
        vat = Decimal(args.vat).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    elif args.reverse_charge:
        # Samonaliczenie VAT należnego od kwoty netto wg stawki krajowej.
        vat = (netto * vat_rate / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        parser.error("--vat wymagany (albo uzyj --reverse-charge by policzyc z netto*stawka)")
    brutto = (netto + vat).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    deduction_pct = Decimal(args.vat_deduction_pct)
    if not (Decimal("0") <= deduction_pct <= Decimal("100")):
        parser.error("--vat-deduction-pct musi byc w zakresie 0-100")

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
        vat_rate=vat_rate,
        vat_deduction_pct=deduction_pct,
        reverse_charge=args.reverse_charge,
        file_path=args.file_path,
        notes=args.notes,
    )
    save_expense(record)

    deductible_vat = (vat * deduction_pct / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    result = {
        "id": record.id,
        "seller": args.seller_name,
        "document_number": args.document_number,
        "issue_date": issue.isoformat(),
        "receive_date": receive.isoformat(),
        "netto": str(netto),
        "vat": str(vat),
        "brutto": str(brutto),
        "vat_deduction_pct": str(deduction_pct),
        "deductible_vat": str(deductible_vat),
        "reverse_charge": args.reverse_charge,
        "category": args.category,
        "status": "saved",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
