#!/usr/bin/env python3
"""Generator JPK_EWP — Ewidencja Przychodow ryczaltowca (roczna)."""

import argparse
import json
from decimal import Decimal

from jdg_ksiegowy.config import DATA_DIR
from jdg_ksiegowy.registry.repository import InvoiceRepository
from jdg_ksiegowy.tax.ewp import save_jpk_ewp


def main():
    parser = argparse.ArgumentParser(description="Generator JPK_EWP (ryczalt, roczna)")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument(
        "--ryczalt-rate",
        type=str,
        default=None,
        help="Stawka ryczaltu (procent). Domyslnie z .env (SELLER_RYCZALT_RATE).",
    )
    args = parser.parse_args()

    # Rok wg daty uzyskania przychodu (art. 14 ust. 1c) — ta sama regula co PIT-28,
    # inaczej faktura zaliczkowa na przelomie roku trafia do innego roku niz zeznanie.
    invoices = InvoiceRepository().list(year=args.year, by="income")

    rate = Decimal(args.ryczalt_rate) if args.ryczalt_rate else None
    output_path = DATA_DIR / "jpk" / f"JPK_EWP_{args.year}.xml"
    save_jpk_ewp(invoices, args.year, output_path, ryczalt_rate=rate)

    total = sum((inv.total_net for inv in invoices), Decimal("0"))
    result = {
        "year": args.year,
        "invoice_count": len(invoices),
        "total_revenue": f"{total:.2f}",
        "file_path": str(output_path),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
