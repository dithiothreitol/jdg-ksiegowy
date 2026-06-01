#!/usr/bin/env python3
"""Odpytanie inboxu KSeF — faktury zakupowe (rola nabywcy) -> rejestr kosztow.

Uzycie:
    python3 inbox.py --month 5 --year 2026          # preview faktur z maja
    python3 inbox.py --date-from 2026-05-01 --date-to 2026-05-31
    python3 inbox.py --month 5 --year 2026 --save    # pobierz XML + zapisz koszty

Bez --save pokazuje liste do akceptacji (status: new|exists|manual); z --save
pobiera XML i zapisuje nowe faktury do SQLite. Korekty/waluty obce/samofakturowanie
nie sa auto-zapisywane (status: manual) — wymagaja swiadomej decyzji.
"""

import argparse
import json
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from jdg_ksiegowy.config import DATA_DIR
from jdg_ksiegowy.expenses.ksef_mapper import metadata_to_record, needs_manual_review
from jdg_ksiegowy.expenses.models import ExpenseCategory
from jdg_ksiegowy.ksef.client import KSeFClient
from jdg_ksiegowy.registry.db import get_expenses, init_db, save_expense

XML_DIR = DATA_DIR / "expenses_xml"


def _resolve_range(args) -> tuple[date, date]:
    if args.date_from and args.date_to:
        return date.fromisoformat(args.date_from), date.fromisoformat(args.date_to)
    today = date.today()
    month = args.month or today.month
    year = args.year or today.year
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end - timedelta(days=1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Odpytanie inboxu KSeF (faktury zakupowe)")
    parser.add_argument("--date-from", help="Poczatek zakresu (YYYY-MM-DD)")
    parser.add_argument("--date-to", help="Koniec zakresu (YYYY-MM-DD)")
    parser.add_argument("--month", type=int, help="Miesiac (1-12); domyslnie biezacy")
    parser.add_argument("--year", type=int, help="Rok; domyslnie biezacy")
    parser.add_argument("--role", default="buyer", choices=["buyer", "seller"])
    parser.add_argument("--seller-nip", default=None, help="Filtruj po NIP sprzedawcy")
    parser.add_argument(
        "--include-corrections",
        action="store_true",
        help="Pokaz tez faktury korygujace (domyslnie pomijane)",
    )
    parser.add_argument(
        "--category",
        default=None,
        choices=[c.value for c in ExpenseCategory],
        help="Wymus kategorie (domyslnie heurystyka po nazwie sprzedawcy)",
    )
    parser.add_argument(
        "--vat-deduction-pct",
        default="100",
        help="Procent VAT odliczalnego (0-100). 50 = auto osobowe mieszane.",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Pobierz XML i zapisz nowe faktury do rejestru (inaczej tylko preview)",
    )
    args = parser.parse_args()

    client = KSeFClient()
    if not client.is_configured():
        print(
            json.dumps(
                {
                    "success": False,
                    "error": "KSeF nie skonfigurowany — ustaw KSEF_NIP i KSEF_TOKEN w .env",
                },
                ensure_ascii=False,
            )
        )
        sys.exit(1)

    date_from, date_to = _resolve_range(args)
    if date_from > date_to:
        print(
            json.dumps(
                {"success": False, "error": "date-from jest pozniejsze niz date-to"},
                ensure_ascii=False,
            )
        )
        sys.exit(1)

    category = ExpenseCategory(args.category) if args.category else None
    deduction = Decimal(args.vat_deduction_pct)

    try:
        metadata = client.query_inbox(
            date_from,
            date_to,
            role=args.role,
            include_corrections=args.include_corrections,
            seller_nip=args.seller_nip,
        )
    except Exception as e:  # blad sieci/SDK na granicy systemu
        print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)

    init_db()
    existing = get_expenses()
    existing_ids = {e.id for e in existing}
    existing_ksef = {e.ksef_number for e in existing if e.ksef_number}

    if args.save:
        XML_DIR.mkdir(parents=True, exist_ok=True)

    invoices = []
    saved_count = 0
    for meta in metadata:
        record = metadata_to_record(meta, category=category, vat_deduction_pct=deduction)
        manual_reason = needs_manual_review(meta)
        already = record.id in existing_ids or meta.ksef_number in existing_ksef

        if already:
            status = "exists"
        elif manual_reason:
            status = "manual"
        elif args.save:
            file_path = None
            try:
                xml = client.download_invoice_xml(meta.ksef_number)
                file_path = XML_DIR / f"{meta.ksef_number.replace('/', '_')}.xml"
                file_path.write_bytes(xml)
                record.file_path = str(file_path.resolve())
            except Exception as e:  # metadane sa, XML chwilowo niedostepny
                record.notes = "; ".join(filter(None, [record.notes, f"brak XML: {e}"]))
            save_expense(record)
            existing_ids.add(record.id)
            existing_ksef.add(meta.ksef_number)
            saved_count += 1
            status = "saved"
        else:
            status = "new"

        invoices.append(
            {
                "ksef_number": meta.ksef_number,
                "invoice_number": meta.invoice_number,
                "seller_name": record.seller_name,
                "seller_nip": record.seller_nip,
                "issue_date": record.issue_date.isoformat(),
                "receive_date": record.receive_date.isoformat(),
                "net": str(record.total_net),
                "vat": str(record.total_vat),
                "gross": str(record.total_gross),
                "currency": meta.currency,
                "vat_rate": str(record.vat_rate),
                "vat_deduction_pct": str(record.vat_deduction_pct),
                "category": record.category,
                "invoice_type": meta.invoice_type,
                "status": status,
                "manual_reason": manual_reason,
                "notes": record.notes,
                "file_path": record.file_path,
            }
        )

    print(
        json.dumps(
            {
                "success": True,
                "env": client.env,
                "role": args.role,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "count": len(invoices),
                "saved": args.save,
                "saved_count": saved_count,
                "invoices": invoices,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
