#!/usr/bin/env python3
"""Raport PIT-28 roczny z danych rejestrowanych faktur."""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from jdg_ksiegowy.tax.pit28 import format_pit28_text, generate_pit28_report


def main():
    parser = argparse.ArgumentParser(description="Raport PIT-28 roczny")
    parser.add_argument(
        "--year",
        type=int,
        default=date.today().year - 1,
        help="Rok podatkowy (domyslnie rok poprzedni)",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    report = generate_pit28_report(args.year)

    if args.format == "json":
        out = {
            "year": report.year,
            "seller_name": report.seller_name,
            "seller_nip": report.seller_nip,
            "ryczalt_rate": str(report.ryczalt_rate),
            "annual_sales_net": f"{report.annual_sales_net:.2f}",
            "annual_ryczalt": f"{report.annual_ryczalt:.2f}",
            "annual_ryczalt_rounded": str(report.annual_ryczalt_rounded),
            "monthly": [
                {
                    "month": m.month,
                    "sales_net": f"{m.sales_net:.2f}",
                    "ryczalt": f"{m.ryczalt:.2f}",
                }
                for m in report.monthly
                if m.sales_net > 0
            ],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(format_pit28_text(report))


if __name__ == "__main__":
    main()
