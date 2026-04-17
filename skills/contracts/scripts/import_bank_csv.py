#!/usr/bin/env python3
"""Import wyciągu bankowego CSV i auto-dopasowanie płatności do faktur."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from jdg_ksiegowy.registry.db import get_invoices, init_db
from jdg_ksiegowy.registry.payments import mark_paid, match_payments, parse_bank_csv


def main():
    parser = argparse.ArgumentParser(description="Import CSV z banku i dopasowanie platnosci")
    parser.add_argument("csv_path", help="Sciezka do pliku CSV z banku")
    parser.add_argument(
        "--auto-mark",
        action="store_true",
        help="Automatycznie oznacz dopasowane faktury jako zaplacone",
    )
    args = parser.parse_args()

    init_db()
    bank_rows = parse_bank_csv(args.csv_path)
    invoices = get_invoices()
    match = match_payments(bank_rows, invoices)

    out: dict = {
        "matched": [],
        "unmatched_bank": len(match.unmatched_bank),
        "unmatched_invoices": [i.number for i in match.unmatched_invoices],
    }

    for row, inv in match.matched:
        entry = {
            "invoice": inv.number,
            "amount": str(row.amount),
            "date": row.transaction_date.isoformat(),
            "description": row.description[:80],
            "marked_paid": False,
        }
        if args.auto_mark:
            from datetime import datetime

            r = mark_paid(inv.number, datetime.combine(row.transaction_date, datetime.min.time()))
            entry["marked_paid"] = r.success
        out["matched"].append(entry)

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
