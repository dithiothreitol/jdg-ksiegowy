#!/usr/bin/env python3
"""Dashboard JDG: nadchodzace terminy, zalegle faktury, podsumowanie miesiaca."""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from jdg_ksiegowy.status import Dashboard


def main():
    parser = argparse.ArgumentParser(description="Dashboard JDG")
    parser.add_argument(
        "--date",
        default=None,
        help="Punkt odniesienia (YYYY-MM-DD), domyslnie dzis",
    )
    parser.add_argument(
        "--format",
        choices=("json", "table"),
        default="json",
        help="Format wyjscia",
    )
    args = parser.parse_args()

    today = date.fromisoformat(args.date) if args.date else date.today()
    snap = Dashboard(today=today).snapshot()

    if args.format == "json":
        out = {
            "today": snap.today.isoformat(),
            "reminders": [
                {
                    "label": r.label,
                    "due_date": r.due_date.isoformat(),
                    "amount": str(r.amount) if r.amount is not None else None,
                    "level": r.level.value,
                    "days_until": r.days_until,
                }
                for r in snap.reminders
            ],
            "unpaid_invoices": [
                {
                    "number": i.number,
                    "buyer": i.buyer_name,
                    "gross": str(i.total_gross),
                    "due": i.payment_due.isoformat(),
                }
                for i in snap.unpaid_invoices
            ],
            "overdue_invoices": [
                {
                    "number": i.number,
                    "buyer": i.buyer_name,
                    "gross": str(i.total_gross),
                    "due": i.payment_due.isoformat(),
                }
                for i in snap.overdue_invoices
            ],
            "month_summary": {
                "sales_net": f"{snap.month_sales_net:.2f}",
                "sales_vat": f"{snap.month_sales_vat:.2f}",
                "expenses_net": f"{snap.month_expenses_net:.2f}",
                "expenses_vat": f"{snap.month_expenses_vat:.2f}",
                "estimated_ryczalt": f"{snap.estimated_ryczalt:.2f}",
                "estimated_zus_health": f"{snap.estimated_zus:.2f}",
            },
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    # table format — kompaktowy dashboard czytelny w terminalu
    print(f"=== Dashboard JDG ({snap.today.isoformat()}) ===\n")
    print("TERMINY:")
    for r in snap.reminders:
        amt = f"  {r.amount} PLN" if r.amount else ""
        marker = {"overdue": "❌", "urgent": "🔥", "warn": "⚠️ ", "info": "  "}[r.level.value]
        print(f"  {marker} [{r.due_date}] {r.label}{amt} ({r.days_until}d)")
    print(f"\nFAKTURY PO TERMINIE ({len(snap.overdue_invoices)}):")
    for i in snap.overdue_invoices:
        print(f"  ❌ {i.number} {i.buyer_name}: {i.total_gross} PLN, due {i.payment_due}")
    print(f"\nFAKTURY NIEZAPLACONE ({len(snap.unpaid_invoices)}):")
    for i in snap.unpaid_invoices:
        print(f"  • {i.number} {i.buyer_name}: {i.total_gross} PLN, due {i.payment_due}")
    print(f"\nMIESIAC {snap.today.strftime('%m/%Y')}:")
    print(f"  Sprzedaz: {snap.month_sales_net:.2f} netto, {snap.month_sales_vat:.2f} VAT")
    print(f"  Koszty:   {snap.month_expenses_net:.2f} netto, {snap.month_expenses_vat:.2f} VAT")
    print(f"  Est. ryczalt: {snap.estimated_ryczalt:.2f} PLN")
    print(f"  Est. ZUS zdrowotne: {snap.estimated_zus:.2f} PLN")


if __name__ == "__main__":
    main()
