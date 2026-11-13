#!/usr/bin/env python3
"""Uzupelnij numery KSeF faktur wyslanych przed poprawka klienta (domyslnie podglad).

python3 backfill.py            # pokaz dopasowania, nic nie zapisuj
python3 backfill.py --apply    # zapisz numery KSeF w rejestrze
"""

import argparse
import json
import sys
from datetime import date

from jdg_ksiegowy.ksef.backfill import backfill_ksef_numbers
from jdg_ksiegowy.ksef.client import KSeFClient
from jdg_ksiegowy.registry.repository import InvoiceRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Uzupelnienie numerow KSeF w rejestrze")
    parser.add_argument("--apply", action="store_true", help="Zapisz numery (inaczej podglad)")
    args = parser.parse_args()

    client = KSeFClient()
    if not client.is_configured():
        print(json.dumps({"success": False, "error": "KSeF nie skonfigurowany"}))
        sys.exit(1)

    result = backfill_ksef_numbers(
        client, InvoiceRepository(), today=date.today(), apply=args.apply
    )
    print(
        json.dumps(
            {
                "success": True,
                "env": client.env,
                "applied": result.applied,
                "matched": [
                    {
                        "invoice": m.invoice_number,
                        "ksef_number": m.ksef_number,
                        "acquired_at": m.acquired_at.isoformat() if m.acquired_at else None,
                    }
                    for m in result.matched
                ],
                "missing": result.missing,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
