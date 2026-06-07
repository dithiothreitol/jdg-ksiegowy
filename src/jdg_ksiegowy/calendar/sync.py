"""Synchronizacja terminow podatkowych z Google Calendar (reconcile, idempotentny).

Zrodlo prawdy: Dashboard.snapshot().reminders (terminy podatkowe + faktury). Kazde
przypomnienie ma stabilny `key`; mapujemy je na wydarzenia calodniowe i uzgadniamy
ze stanem kalendarza: tworzymy brakujace, aktualizujemy zmienione, usuwamy osierocone
(np. po oznaczeniu faktury jako zaplaconej).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from jdg_ksiegowy.calendar.gcal import KEY_PROP, GCalClient
from jdg_ksiegowy.status.dashboard import Dashboard, Reminder


@dataclass(frozen=True)
class DesiredEvent:
    key: str
    summary: str
    day: date
    description: str


@dataclass
class SyncResult:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    dry_run: bool = False


def _fmt_amount(amount: Decimal | None) -> str:
    """1234.5 -> '1 234,50 zł' (separator tysiecy = spacja, dziesietny = przecinek)."""
    if amount is None:
        return ""
    s = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
    return f"{s} zł"


def _summary(reminder: Reminder) -> str:
    amt = _fmt_amount(reminder.amount)
    return f"{reminder.label}: {amt}" if amt else reminder.label


def reminders_to_events(reminders: list[Reminder]) -> list[DesiredEvent]:
    """Zamien przypomnienia (z kluczem) na pozadane wydarzenia kalendarza."""
    events: list[DesiredEvent] = []
    for r in reminders:
        if not r.key:
            continue  # bez stabilnego klucza pomijamy (ochrona idempotencji)
        desc = [f"Termin: {r.due_date.isoformat()}"]
        if r.amount is not None:
            desc.insert(0, f"Kwota (szacunkowo): {_fmt_amount(r.amount)}")
        desc.append("Wygenerowano automatycznie przez JDG-Ksiegowy.")
        events.append(
            DesiredEvent(
                key=r.key, summary=_summary(r), day=r.due_date, description="\n".join(desc)
            )
        )
    return events


def _needs_update(event: dict, desired: DesiredEvent) -> bool:
    if event.get("summary") != desired.summary:
        return True
    start = (event.get("start") or {}).get("date")
    return start != desired.day.isoformat()


def sync_reminders(
    today: date | None = None,
    *,
    dry_run: bool = False,
    client: GCalClient | None = None,
) -> SyncResult:
    """Uzgodnij terminy z kalendarzem. `client` wstrzykiwalny (testy)."""
    snap = Dashboard(today=today).snapshot()
    desired = reminders_to_events(snap.reminders)
    client = client or GCalClient()
    result = SyncResult(dry_run=dry_run)

    cal_id = client.ensure_calendar()
    by_key: dict[str, dict] = {}
    for ev in client.list_managed_events(cal_id):
        k = ev.get("extendedProperties", {}).get("private", {}).get(KEY_PROP)
        if k:
            by_key[k] = ev
    desired_keys = {d.key for d in desired}

    for d in desired:
        existing = by_key.get(d.key)
        if existing is None:
            if not dry_run:
                client.upsert_event(
                    cal_id, key=d.key, summary=d.summary, day=d.day, description=d.description
                )
            result.created.append(d.key)
        elif _needs_update(existing, d):
            if not dry_run:
                client.upsert_event(
                    cal_id,
                    key=d.key,
                    summary=d.summary,
                    day=d.day,
                    description=d.description,
                    existing_event_id=existing["id"],
                )
            result.updated.append(d.key)
        else:
            result.unchanged.append(d.key)

    for key, ev in by_key.items():
        if key not in desired_keys:
            if not dry_run:
                client.delete_event(cal_id, ev["id"])
            result.deleted.append(key)

    return result
