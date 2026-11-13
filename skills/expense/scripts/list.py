#!/usr/bin/env python3
"""Wylistuj faktury zakupu z rejestru za dany miesiac."""

import argparse
import json

from jdg_ksiegowy.registry.repository import ExpenseRepository


def main():
    parser = argparse.ArgumentParser(description="Lista faktur zakupu")
    parser.add_argument("--month", type=int, default=None)
    parser.add_argument("--year", type=int, default=None)
    args = parser.parse_args()

    records = ExpenseRepository().list(year=args.year, month=args.month)

    out = {
        "count": len(records),
        "expenses": [
            {
                "id": r.id,
                "seller": r.seller_name,
                "nip": r.seller_nip,
                "document_number": r.document_number,
                "issue_date": r.issue_date.isoformat(),
                "receive_date": r.receive_date.isoformat(),
                "category": r.category.value,
                "netto": str(r.total_net),
                "vat": str(r.total_vat),
                "brutto": str(r.total_gross),
                "vat_deduction_pct": str(r.vat_deduction_pct),
                "file_path": r.file_path,
            }
            for r in records
        ],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
