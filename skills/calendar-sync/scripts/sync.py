#!/usr/bin/env python3
"""Synchronizacja terminow podatkowych JDG z Google Calendar.

Uzycie:
    python3 sync.py --dry-run      # podglad roznicy, nic nie zapisuje
    python3 sync.py                # tworzy/aktualizuje/usuwa wydarzenia

Idempotentne — bezpieczne do uruchamiania cronem codziennie.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from jdg_ksiegowy.calendar.gcal import GCalError
from jdg_ksiegowy.calendar.sync import sync_reminders
from jdg_ksiegowy.config import settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronizacja terminow z Google Calendar")
    parser.add_argument(
        "--dry-run", action="store_true", help="Podglad roznicy bez zapisu do kalendarza"
    )
    parser.add_argument("--today", default=None, help="Data odniesienia YYYY-MM-DD (do testow)")
    args = parser.parse_args()

    if not settings.calendar.is_configured():
        print(
            json.dumps(
                {
                    "success": False,
                    "error": (
                        "Google Calendar nie skonfigurowany — ustaw GCAL_ENABLED=true i "
                        "GCAL_CREDENTIALS_PATH w .env, potem uruchom "
                        "python -m jdg_ksiegowy.calendar.auth_setup"
                    ),
                },
                ensure_ascii=False,
            )
        )
        sys.exit(1)

    today = date.fromisoformat(args.today) if args.today else None
    try:
        result = sync_reminders(today=today, dry_run=args.dry_run)
    except GCalError as e:
        print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)

    print(
        json.dumps(
            {
                "success": True,
                "dry_run": result.dry_run,
                "created": result.created,
                "updated": result.updated,
                "deleted": result.deleted,
                "unchanged": result.unchanged,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
