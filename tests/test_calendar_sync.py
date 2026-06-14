"""Testy synchronizacji terminow z Google Calendar — fake klient, zero sieci."""

from datetime import date
from decimal import Decimal

from jdg_ksiegowy.calendar.sync import (
    SyncResult,
    _fmt_amount,
    reminders_to_events,
    sync_reminders,
)
from jdg_ksiegowy.status.dashboard import Dashboard, Reminder, ReminderLevel

TODAY = date(2026, 6, 7)  # poprzedni miesiac = maj -> klucze *-2026-05


class FakeGCal:
    """Atrapa GCalClient — rejestruje wywolania zapisu, zwraca wstrzyknięte eventy."""

    def __init__(self, existing: list[dict] | None = None):
        self.existing = existing or []
        self.created: list[str] = []
        self.updated: list[str] = []
        self.deleted: list[str] = []
        self.calendar_ensured = False

    def ensure_calendar(self) -> str:
        self.calendar_ensured = True
        return "cal1"

    def list_managed_events(self, calendar_id: str) -> list[dict]:
        return list(self.existing)

    def upsert_event(self, calendar_id, *, key, summary, day, description, existing_event_id=None):
        if existing_event_id:
            self.updated.append(key)
            return "updated"
        self.created.append(key)
        return "created"

    def delete_event(self, calendar_id, event_id):
        self.deleted.append(event_id)


def _event(key: str, summary: str, day_iso: str, event_id: str) -> dict:
    return {
        "id": event_id,
        "summary": summary,
        "start": {"date": day_iso},
        "extendedProperties": {"private": {"jdg_managed": "1", "jdg_key": key}},
    }


# --- formatowanie kwot (asercje bez literalu separatora tysiecy) ---


def test_fmt_amount_polish_format():
    out = _fmt_amount(Decimal("2520.00"))
    assert out.startswith("2") and "520,00" in out and out.endswith("zł")
    small = _fmt_amount(Decimal("5.00"))
    assert small.startswith("5,00") and small.endswith("zł")
    assert _fmt_amount(None) == ""


# --- mapowanie przypomnien -> wydarzenia ---


def test_reminders_to_events_key_and_summary():
    rem = Reminder(
        label="Ryczalt za 05/2026",
        due_date=date(2026, 6, 20),
        amount=Decimal("2520.00"),
        level=ReminderLevel.INFO,
        days_until=13,
        key="ryczalt-2026-05",
    )
    events = reminders_to_events([rem])
    assert len(events) == 1
    assert events[0].key == "ryczalt-2026-05"
    assert events[0].day == date(2026, 6, 20)
    assert events[0].summary.startswith("Ryczalt za 05/2026:")
    assert "520,00" in events[0].summary


def test_reminder_without_key_skipped():
    rem = Reminder("X", date(2026, 6, 20), None, ReminderLevel.INFO, 13, key="")
    assert reminders_to_events([rem]) == []


# --- reconcile: create / idempotent / update / delete / dry-run ---


def test_sync_creates_tax_reminders_on_empty_calendar(isolated_db):
    fake = FakeGCal()
    result = sync_reminders(today=TODAY, client=fake)
    assert fake.calendar_ensured
    assert set(result.created) == {"ryczalt-2026-05", "zus-2026-05", "vat_jpk-2026-05"}
    assert not result.updated and not result.deleted


def test_sync_idempotent(isolated_db):
    snap = Dashboard(today=TODAY).snapshot()
    desired = reminders_to_events(snap.reminders)
    existing = [
        _event(d.key, d.summary, d.day.isoformat(), f"ev{i}") for i, d in enumerate(desired)
    ]
    fake = FakeGCal(existing=existing)

    result = sync_reminders(today=TODAY, client=fake)

    assert len(result.unchanged) == len(desired)
    assert not result.created and not result.updated and not result.deleted
    assert not fake.created and not fake.updated and not fake.deleted


def test_sync_updates_changed_summary(isolated_db):
    snap = Dashboard(today=TODAY).snapshot()
    desired = reminders_to_events(snap.reminders)
    stale = [_event(desired[0].key, "STARA TRESC", desired[0].day.isoformat(), "ev0")]
    fake = FakeGCal(existing=stale)

    result = sync_reminders(today=TODAY, client=fake)

    assert desired[0].key in result.updated
    assert desired[0].key in fake.updated


def test_sync_deletes_orphan_event(isolated_db):
    orphan = [_event("invoice-A1/05/2026", "Faktura A1/05/2026", "2026-06-01", "evX")]
    fake = FakeGCal(existing=orphan)

    result = sync_reminders(today=TODAY, client=fake)

    assert "invoice-A1/05/2026" in result.deleted
    assert fake.deleted == ["evX"]


def test_dry_run_writes_nothing(isolated_db):
    fake = FakeGCal()
    result = sync_reminders(today=TODAY, dry_run=True, client=fake)
    assert result.dry_run is True
    assert len(result.created) == 3
    assert fake.created == []


# --- kwota VAT liczona (nie None) ---


def test_vat_reminder_has_amount(isolated_db):
    from jdg_ksiegowy.registry.db import InvoiceRecord, init_db, save_invoice

    init_db()
    save_invoice(
        InvoiceRecord(
            id="i-may",
            number="A1/05/2026",
            issue_date=date(2026, 5, 10),
            sale_date=date(2026, 5, 10),
            payment_due=date(2026, 5, 24),
            buyer_name="Klient",
            buyer_nip="1234567890",
            total_net=Decimal("1000"),
            total_vat=Decimal("230"),
            total_gross=Decimal("1230"),
            vat_rate=Decimal("23"),
            paid_at=None,
        )
    )
    snap = Dashboard(today=TODAY).snapshot()
    vat_rem = next(r for r in snap.reminders if r.key == "vat_jpk-2026-05")
    assert vat_rem.amount == Decimal("230")


def test_sync_result_default_lists():
    r = SyncResult()
    assert r.created == [] and r.dry_run is False
