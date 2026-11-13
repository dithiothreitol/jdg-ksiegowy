#!/usr/bin/env python3
"""Uruchom cykliczne kontrakty — wystawia faktury miesięczne wg harmonogramu."""

import argparse
import json
from datetime import date

from jdg_ksiegowy.contracts.runner import run_contracts


def main():
    parser = argparse.ArgumentParser(description="Cykliczne kontrakty JDG")
    parser.add_argument("--date", default=None, help="Data (YYYY-MM-DD), domyslnie dzis")
    args = parser.parse_args()

    today = date.fromisoformat(args.date) if args.date else date.today()
    result = run_contracts(today=today)

    out = {
        "date": today.isoformat(),
        "generated": result.generated,
        "skipped_count": len(result.skipped),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
