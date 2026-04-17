#!/usr/bin/env python3
"""Wylistuj faktury zakupu z rejestru za dany miesiac."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from jdg_ksiegowy.registry.db import get_expenses, init_db


def main():
    parser = argparse.ArgumentParser(description="Lista faktur zakupu")
    parser.add_argument("--month", type=int, default=None)
    parser.add_argument("--year", type=int, default=None)
    args = parser.parse_args()

    init_db()
    records = get_expenses(args.month, args.year)

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
                "category": r.category,
                "netto": str(r.total_net),
                "vat": str(r.total_vat),
                "brutto": str(r.total_gross),
                "vat_deductible": bool(r.vat_deductible),
                "file_path": r.file_path,
            }
            for r in records
        ],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
