#!/usr/bin/env python3
"""Generator JPK_V7M — AgentSkill dla OpenClaw."""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from jdg_ksiegowy.config import DATA_DIR
from jdg_ksiegowy.expenses.models import Expense, ExpenseCategory
from jdg_ksiegowy.invoice.models import Buyer, Invoice, LineItem
from jdg_ksiegowy.registry.db import get_expenses, get_invoices, init_db
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


def records_to_expenses(records):
    return [
        Expense(
            id=r.id,
            seller_name=r.seller_name,
            seller_nip=r.seller_nip,
            seller_country=r.seller_country or "PL",
            document_number=r.document_number,
            issue_date=r.issue_date,
            receive_date=r.receive_date,
            description=r.description or "",
            category=ExpenseCategory(r.category) if r.category else ExpenseCategory.INNE,
            total_net=Decimal(str(r.total_net)),
            total_vat=Decimal(str(r.total_vat)),
            vat_rate=Decimal(str(r.vat_rate)) if r.vat_rate else Decimal("23"),
            vat_deductible=bool(r.vat_deductible),
            file_path=r.file_path,
            notes=r.notes,
        )
        for r in records
    ]


def main():
    parser = argparse.ArgumentParser(description="Generator JPK_V7M")
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()

    init_db()
    invoice_records = get_invoices(args.month, args.year)
    expense_records = get_expenses(args.month, args.year)
    invoices = records_to_invoices(invoice_records)
    expenses = records_to_expenses(expense_records)

    total_net = sum((Decimal(str(r.total_net)) for r in invoice_records), Decimal("0"))
    total_vat = sum((Decimal(str(r.total_vat)) for r in invoice_records), Decimal("0"))
    exp_net = sum(
        (Decimal(str(r.total_net)) for r in expense_records if r.vat_deductible),
        Decimal("0"),
    )
    exp_vat = sum(
        (Decimal(str(r.total_vat)) for r in expense_records if r.vat_deductible),
        Decimal("0"),
    )

    output_path = DATA_DIR / "jpk" / f"JPK_V7M_{args.year}_{args.month:02d}.xml"
    save_jpk_v7m(invoices, args.month, args.year, output_path, expenses=expenses)

    result = {
        "period": f"{args.month:02d}/{args.year}",
        "invoice_count": len(invoices),
        "expense_count": len(expenses),
        "sales_total_net": f"{total_net:.2f}",
        "sales_total_vat": f"{total_vat:.2f}",
        "expenses_deductible_net": f"{exp_net:.2f}",
        "expenses_deductible_vat": f"{exp_vat:.2f}",
        "vat_to_pay": f"{max(total_vat - exp_vat, Decimal('0')):.2f}",
        "file_path": str(output_path),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
