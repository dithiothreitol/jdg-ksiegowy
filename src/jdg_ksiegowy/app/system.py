"""Przypadki uzycia: status ksiegowosci, diagnostyka, kalendarz, backup, konfiguracja."""

from __future__ import annotations

import io
import os
import sqlite3
import tarfile
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import ClassVar

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel

from jdg_ksiegowy.app.audit import audit
from jdg_ksiegowy.app.errors import ConfigMissingError, ExternalServiceError, InvalidInputError
from jdg_ksiegowy.app.invoices import InvoiceView
from jdg_ksiegowy.config import DATA_DIR, ENV_FILE, JDG_HOME, settings
from jdg_ksiegowy.doctor import run_doctor
from jdg_ksiegowy.registry.db import init_db
from jdg_ksiegowy.status.dashboard import Dashboard

# --- Status -----------------------------------------------------------------------


class ReminderView(BaseModel):
    table_columns: ClassVar[tuple[str, ...]] = ("due_date", "label", "amount", "level")

    key: str
    label: str
    due_date: date
    amount: Decimal | None
    level: str
    days_until: int


class StatusView(BaseModel):
    today: date
    reminders: list[ReminderView]
    unpaid_invoices: list[InvoiceView]
    overdue_invoices: list[InvoiceView]
    month_sales_net: Decimal
    month_sales_vat: Decimal
    month_expenses_net: Decimal
    month_expenses_vat: Decimal
    estimated_ryczalt: Decimal
    estimated_zus_health: Decimal


def status(today: date | None = None) -> StatusView:
    snap = Dashboard(today=today).snapshot()
    return StatusView(
        today=snap.today,
        reminders=[
            ReminderView(
                key=r.key,
                label=r.label,
                due_date=r.due_date,
                amount=r.amount,
                level=r.level.value,
                days_until=r.days_until,
            )
            for r in snap.reminders
        ],
        unpaid_invoices=[InvoiceView.of(i) for i in snap.unpaid_invoices],
        overdue_invoices=[InvoiceView.of(i) for i in snap.overdue_invoices],
        month_sales_net=snap.month_sales_net,
        month_sales_vat=snap.month_sales_vat,
        month_expenses_net=snap.month_expenses_net,
        month_expenses_vat=snap.month_expenses_vat,
        estimated_ryczalt=snap.estimated_ryczalt,
        estimated_zus_health=snap.estimated_zus,
    )


# --- Doctor ------------------------------------------------------------------------


class FindingView(BaseModel):
    level: str
    area: str
    message: str


class DoctorView(BaseModel):
    ok_count: int
    warnings: int
    errors: int
    findings: list[FindingView]


def doctor() -> DoctorView:
    report = run_doctor()
    return DoctorView(
        ok_count=report.ok_count,
        warnings=len(report.warnings),
        errors=len(report.errors),
        findings=[
            FindingView(level=f.level, area=f.area, message=f.message) for f in report.findings
        ],
    )


# --- Kalendarz ---------------------------------------------------------------------


class CalendarSyncView(BaseModel):
    dry_run: bool
    created: list[str]
    updated: list[str]
    deleted: list[str]
    unchanged: list[str]


def calendar_sync(*, dry_run: bool = False, today: date | None = None) -> CalendarSyncView:
    if not settings.calendar.is_configured():
        raise ConfigMissingError(
            "Google Calendar nie skonfigurowany",
            hint=(
                "Ustaw GCAL_ENABLED=true i GCAL_CREDENTIALS_PATH w .env, potem "
                "`uv run python -m jdg_ksiegowy.calendar.auth_setup`."
            ),
        )
    from jdg_ksiegowy.calendar.gcal import GCalError
    from jdg_ksiegowy.calendar.sync import sync_reminders

    errors: tuple[type[Exception], ...] = (GCalError,)
    try:
        from googleapiclient.errors import HttpError

        errors = (GCalError, HttpError)
    except ImportError:
        pass
    try:
        result = sync_reminders(today=today, dry_run=dry_run)
    except errors as e:
        raise ExternalServiceError(f"Google Calendar: {e}") from e
    if not dry_run:
        audit("calendar.sync", None, "ok", {"created": len(result.created)})
    return CalendarSyncView(
        dry_run=result.dry_run,
        created=result.created,
        updated=result.updated,
        deleted=result.deleted,
        unchanged=result.unchanged,
    )


# --- Backup ------------------------------------------------------------------------

BACKUP_DIRS = ("upo", "faktury", "jpk", "mf_cert", "zus", "expenses_xml")
BACKUP_GLOB = "jdg_backup_*.tar.gz.fernet"


class BackupView(BaseModel):
    path: str
    size_bytes: int
    plain_bytes: int
    verified: bool
    removed: list[str]


def _backup_dir() -> Path:
    if settings.backup_dir:
        return Path(settings.backup_dir).expanduser()
    onedrive = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer")
    if onedrive and Path(onedrive).is_dir():
        return Path(onedrive) / "Backups" / "jdg-ksiegowy"
    return Path.home() / "Documents" / "jdg-ksiegowy-backups"


def _db_file() -> Path:
    url = settings.db_url
    if not url.startswith("sqlite:///"):
        raise InvalidInputError("Backup obsluguje tylko baze SQLite")
    return Path(url.removeprefix("sqlite:///"))


def _archive() -> bytes:
    """tar.gz: spojna kopia bazy (VACUUM INTO — bezpieczne przy WAL i pracy w tle) + dokumenty."""
    init_db()
    buf = io.BytesIO()
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "jdg_ksiegowy.db"
        with sqlite3.connect(_db_file()) as conn:
            conn.execute("VACUUM INTO ?", (str(snapshot),))
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            tar.add(snapshot, arcname="jdg_ksiegowy.db")
            for name in BACKUP_DIRS:
                if (DATA_DIR / name).exists():
                    tar.add(DATA_DIR / name, arcname=name)
    return buf.getvalue()


def _verify(blob: bytes, fernet: Fernet) -> None:
    """Odszyfruj, rozpakuj baze i sprawdz jej integralnosc."""
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(fileobj=io.BytesIO(fernet.decrypt(blob)), mode="r:gz") as tar:
            tar.extract("jdg_ksiegowy.db", path=tmp, filter="data")
        with sqlite3.connect(Path(tmp) / "jdg_ksiegowy.db") as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise ExternalServiceError(f"Kopia bazy w backupie jest uszkodzona: {result}")


def _purge(out_dir: Path, keep_days: int, keep_monthly: int) -> list[str]:
    """Zostaw ostatnie `keep_days` kopii + najstarsza kopie z kazdego z `keep_monthly` mies."""
    files = sorted(out_dir.glob(BACKUP_GLOB), reverse=True)
    keep = set(files[:keep_days])
    months: dict[str, Path] = {}
    for f in files:
        months[f.name.removeprefix("jdg_backup_")[:6]] = f  # nadpisuje -> najstarsza w miesiacu
    keep.update(sorted(months.values(), reverse=True)[:keep_monthly])
    removed = [f for f in files if f not in keep]
    for f in removed:
        f.unlink()
    return [f.name for f in removed]


def backup(
    *, output_dir: Path | None = None, keep_days: int = 30, keep_monthly: int = 12
) -> BackupView:
    """Szyfrowany backup bazy i dokumentow; zawsze weryfikowany po zapisie."""
    if not settings.backup_key:
        raise ConfigMissingError(
            "Brak BACKUP_KEY",
            hint=(
                'Wygeneruj klucz: python -c "from cryptography.fernet import Fernet; '
                'print(Fernet.generate_key().decode())" — dopisz do .env i do menedzera hasel.'
            ),
        )
    try:
        fernet = Fernet(settings.backup_key.encode())
    except (ValueError, InvalidToken) as e:
        raise ConfigMissingError(f"Nieprawidlowy BACKUP_KEY: {e}") from e
    archive = _archive()
    blob = fernet.encrypt(archive)
    out_dir = (output_dir or _backup_dir()).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"jdg_backup_{datetime.now():%Y%m%d_%H%M%S}.tar.gz.fernet"
    path.write_bytes(blob)
    _verify(path.read_bytes(), fernet)
    removed = _purge(out_dir, keep_days, keep_monthly)
    audit("backup", path.name, "ok", {"bytes": len(blob)})
    return BackupView(
        path=str(path),
        size_bytes=len(blob),
        plain_bytes=len(archive),
        verified=True,
        removed=removed,
    )


# --- Konfiguracja ------------------------------------------------------------------


class ConfigView(BaseModel):
    jdg_home: str
    env_file: str
    env_file_exists: bool
    data_dir: str
    database: str
    ksef_env: str
    mf_env: str
    seller_nip: str
    seller_name: str
    secrets_set: dict[str, bool]


def show_config() -> ConfigView:
    """Konfiguracja efektywna — sekrety tylko jako informacja ustawiony/nieustawiony."""
    return ConfigView(
        jdg_home=str(JDG_HOME),
        env_file=str(ENV_FILE),
        env_file_exists=ENV_FILE.exists(),
        data_dir=str(DATA_DIR),
        database=settings.db_url,
        ksef_env=settings.ksef.env,
        mf_env=settings.mf.env,
        seller_nip=settings.seller.nip,
        seller_name=settings.seller.name,
        secrets_set={
            "KSEF_TOKEN": bool(settings.ksef.token),
            "MF_PESEL": bool(settings.mf.pesel),
            "SMTP_PASSWORD": bool(settings.smtp.password),
            "ANTHROPIC_API_KEY": bool(settings.anthropic_api_key),
            "BACKUP_KEY": bool(settings.backup_key),
        },
    )
