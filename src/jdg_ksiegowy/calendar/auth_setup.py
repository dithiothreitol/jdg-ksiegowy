"""Jednorazowa autoryzacja OAuth do Google Calendar.

Uruchom RAZ na maszynie z przegladarka:
    python -m jdg_ksiegowy.calendar.auth_setup

Wymaga GCAL_CREDENTIALS_PATH (OAuth client secrets JSON typu "Desktop app" z Google
Cloud Console). Otwiera przegladarke, prosi o zgode i zapisuje refresh token do
GCAL_TOKEN_PATH — od tego momentu sync dziala headless.
"""

from __future__ import annotations

import sys
from pathlib import Path

from jdg_ksiegowy.calendar.gcal import SCOPES
from jdg_ksiegowy.config import settings


def main() -> None:
    cfg = settings.calendar
    if not cfg.credentials_path:
        print("Ustaw GCAL_CREDENTIALS_PATH w .env (OAuth client secrets JSON z Google Cloud).")
        sys.exit(1)
    if not Path(cfg.credentials_path).exists():
        print(f"Plik credentials nie istnieje: {cfg.credentials_path}")
        sys.exit(1)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Brak biblioteki. Zainstaluj: pip install google-auth-oauthlib")
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(cfg.credentials_path, SCOPES)
    creds = flow.run_local_server(port=0)

    token_path = Path(cfg.token_path)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    print(f"OK — token zapisany: {token_path}")
    print("Ustaw GCAL_ENABLED=true w .env i uruchom skill calendar-sync.")


if __name__ == "__main__":
    main()
