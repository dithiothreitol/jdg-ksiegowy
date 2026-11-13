#!/usr/bin/env python3
"""Oznacz fakture jako zaplacona."""

import argparse
import json
import sys
from datetime import datetime

from jdg_ksiegowy.registry.repository import InvoiceNotFoundError, InvoiceRepository


def main():
    parser = argparse.ArgumentParser(description="Oznacz fakture jako zaplacona")
    parser.add_argument("number", help="Numer faktury, np. A1/04/2026")
    parser.add_argument("--date", default=None, help="Data platnosci (YYYY-MM-DD), domyslnie teraz")
    args = parser.parse_args()

    paid_at = datetime.fromisoformat(args.date) if args.date else datetime.now()
    try:
        InvoiceRepository().mark_paid(args.number, paid_at)
    except (InvoiceNotFoundError, ValueError) as e:
        print(json.dumps({"number": args.number, "success": False, "error": str(e)}))
        sys.exit(1)
    print(json.dumps({"number": args.number, "success": True, "error": ""}))


if __name__ == "__main__":
    main()
