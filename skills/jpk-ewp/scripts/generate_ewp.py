#!/usr/bin/env python3
"""Generator JPK_EWP — Ewidencja Przychodow ryczaltowca (roczna)."""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from jdg_ksiegowy.config import DATA_DIR
from jdg_ksiegowy.invoice.models import Buyer, Invoice, LineItem
from jdg_ksiegowy.registry.db import get_invoices, init_db
from jdg_ksiegowy.tax.ewp import save_jpk_ewp


def records_to_invoices(records):
    return [
        Invoice(
            id=r.id,
            number=r.number,
            issue_date=r.issue_date,
            sale_date=r.sale_date,
            payment_due=r.payment_due,
            buyer=Buyer(name=r.buyer_name, nip=r.buyer_nip, address=r.buyer_address or ""),
            items=[
                LineItem(
                    description="(z rejestru)",
                    unit_price_net=Decimal(str(r.total_net)),
                    vat_rate=Decimal(str(r.vat_rate)) if r.vat_rate else Decimal("23"),
                )
            ],
        )
        for r in records
    ]


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

    init_db()
    invoices = []
    for month in range(1, 13):
        invoices.extend(records_to_invoices(get_invoices(month, args.year)))

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
