"""Klient Google Calendar API — app-native OAuth (refresh token, headless).

Lazy import bibliotek google (jak ksef2 w ksef/client.py), zeby brak zaleznosci
nie wywracal importu reszty aplikacji. Uwierzytelnianie: refresh token zapisany
przez calendar.auth_setup do `GCAL_TOKEN_PATH`.

Idempotencja: wlasne wydarzenia oznaczamy extendedProperties.private:
  jdg_managed=1, jdg_key=<stabilny klucz>
Dzieki temu reconcile dotyka WYLACZNIE wydarzen utworzonych przez aplikacje.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from jdg_ksiegowy.config import settings

SCOPES = ["https://www.googleapis.com/auth/calendar"]
MANAGED_FLAG = "jdg_managed"
KEY_PROP = "jdg_key"


class GCalError(RuntimeError):
    """Blad konfiguracji / uwierzytelniania Google Calendar."""


class GCalClient:
    """Cienki wrapper na Google Calendar API v3."""

    def __init__(self):
        self.cfg = settings.calendar
        self._service = None

    def _build_service(self):
        if self._service is not None:
            return self._service
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError as e:
            raise GCalError(
                "Brak bibliotek Google. Zainstaluj: pip install "
                "google-api-python-client google-auth google-auth-oauthlib"
            ) from e

        token_path = Path(self.cfg.token_path)
        if not token_path.exists():
            raise GCalError(
                f"Brak tokenu OAuth ({token_path}). Uruchom: "
                "python -m jdg_ksiegowy.calendar.auth_setup"
            )

        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                token_path.write_text(creds.to_json(), encoding="utf-8")
            else:
                raise GCalError(
                    "Token OAuth niewazny/odwolany — uruchom ponownie "
                    "python -m jdg_ksiegowy.calendar.auth_setup"
                )
        self._service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return self._service

    # --- kalendarz ---

    def ensure_calendar(self) -> str:
        """Zwroc id kalendarza `GCAL_CALENDAR_NAME`; utworz jesli nie istnieje.

        Kolejnosc zrodel id: config.calendar_id -> data/gcal_state.json -> wyszukanie
        po nazwie -> utworzenie. Wynik persystowany do state_path.
        """
        if self.cfg.calendar_id:
            return self.cfg.calendar_id
        cached = self._read_state().get("calendar_id")
        service = self._build_service()
        if cached and self._calendar_exists(service, cached):
            return cached

        name = self.cfg.calendar_name
        page_token = None
        while True:
            resp = service.calendarList().list(pageToken=page_token).execute()
            for item in resp.get("items", []):
                if item.get("summary") == name:
                    self._write_state(item["id"])
                    return item["id"]
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        created = service.calendars().insert(
            body={"summary": name, "timeZone": self.cfg.timezone}
        ).execute()
        self._write_state(created["id"])
        return created["id"]

    @staticmethod
    def _calendar_exists(service, calendar_id: str) -> bool:
        try:
            service.calendars().get(calendarId=calendar_id).execute()
            return True
        except Exception:
            return False

    def _read_state(self) -> dict:
        p = Path(self.cfg.state_path)
        if not p.exists():
            return {}
        return json.loads(p.read_text(encoding="utf-8"))

    def _write_state(self, calendar_id: str) -> None:
        p = Path(self.cfg.state_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"calendar_id": calendar_id}), encoding="utf-8")

    # --- wydarzenia ---

    def list_managed_events(self, calendar_id: str) -> list[dict]:
        """Wszystkie wydarzenia utworzone przez aplikacje (jdg_managed=1)."""
        service = self._build_service()
        events: list[dict] = []
        page_token = None
        while True:
            resp = (
                service.events()
                .list(
                    calendarId=calendar_id,
                    privateExtendedProperty=f"{MANAGED_FLAG}=1",
                    showDeleted=False,
                    maxResults=2500,
                    pageToken=page_token,
                )
                .execute()
            )
            events.extend(resp.get("items", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return events

    def upsert_event(
        self,
        calendar_id: str,
        *,
        key: str,
        summary: str,
        day: date,
        description: str,
        existing_event_id: str | None = None,
    ) -> str:
        """Utworz lub zaktualizuj wydarzenie calodniowe. Zwraca 'created'|'updated'."""
        service = self._build_service()
        days_before = self.cfg.reminder_days_before
        body = {
            "summary": summary,
            "description": description,
            "start": {"date": day.isoformat()},
            "end": {"date": (day + timedelta(days=1)).isoformat()},
            "extendedProperties": {"private": {MANAGED_FLAG: "1", KEY_PROP: key}},
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": days_before * 24 * 60},
                    {"method": "popup", "minutes": 0},
                ],
            },
        }
        if existing_event_id:
            service.events().patch(
                calendarId=calendar_id, eventId=existing_event_id, body=body
            ).execute()
            return "updated"
        service.events().insert(calendarId=calendar_id, body=body).execute()
        return "created"

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        service = self._build_service()
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
