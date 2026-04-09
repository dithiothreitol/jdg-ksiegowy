#!/usr/bin/env python3
"""Generator JPK_V7M — AgentSkill dla OpenClaw."""

import argparse
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from jdg_ksiegowy.config import DATA_DIR
from jdg_ksiegowy.invoice.models import Buyer, Invoice, LineItem
from jdg_ksiegowy.registry.db import get_invoices, init_db
from jdg_ksiegowy.tax.jpk import save_jpk_v7m


def records_to_invoices(records):
    invoices = []
    for r in records:
        vat_rate = Decimal(str(r.vat_rate)) if r.vat_rate else Decimal("23")
        inv = Invoice(
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
                    vat_rate=vat_rate,
                )
            ],
        )
        invoices.append(inv)
    return invoices


def main():
    parser = argparse.ArgumentParser(description="Generator JPK_V7M")
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()

    init_db()
    records = get_invoices(args.month, args.year)
    invoices = records_to_invoices(records)

    total_net = sum(Decimal(str(r.total_net)) for r in records)
    total_vat = sum(Decimal(str(r.total_vat)) for r in records)

    output_path = DATA_DIR / "jpk" / f"JPK_V7M_{args.year}_{args.month:02d}.xml"
    save_jpk_v7m(invoices, args.month, args.year, output_path)

    result = {
        "period": f"{args.month:02d}/{args.year}",
        "invoice_count": len(invoices),
        "total_net": f"{total_net:.2f}",
        "total_vat": f"{total_vat:.2f}",
        "file_path": str(output_path),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
