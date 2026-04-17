#!/usr/bin/env python3
"""Oznacz fakturę jako zapłaconą."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from jdg_ksiegowy.registry.payments import mark_paid


def main():
    parser = argparse.ArgumentParser(description="Oznacz fakture jako zaplacona")
    parser.add_argument("number", help="Numer faktury, np. A1/04/2026")
    parser.add_argument("--date", default=None, help="Data platnosci (YYYY-MM-DD), domyslnie teraz")
    args = parser.parse_args()

    paid_at = datetime.fromisoformat(args.date) if args.date else None
    result = mark_paid(args.number, paid_at)
    print(json.dumps({"number": result.invoice_number, "success": result.success, "error": result.error}, ensure_ascii=False))
    if not result.success:
        sys.exit(1)


if __name__ == "__main__":
    main()
