"""Backup: spojna kopia bazy (VACUUM INTO), szyfrowanie, weryfikacja, odtworzenie, retencja."""

import io
import pathlib
import sqlite3
import tarfile
from contextlib import closing
from datetime import date
from decimal import Decimal

import pytest
from cryptography.fernet import Fernet

from jdg_ksiegowy.app import system
from jdg_ksiegowy.app.errors import ConfigMissingError
from tests.helpers import InvoiceRow, save_invoice


@pytest.fixture
def key(monkeypatch):
    from jdg_ksiegowy.config import settings

    value = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "backup_key", value)
    return value


def test_backup_restores_to_identical_database(isolated_db, key, tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    (data_dir / "faktury").mkdir(parents=True)
    (data_dir / "faktury" / "f.xml").write_text("<x/>", encoding="utf-8")
    monkeypatch.setattr(system, "DATA_DIR", data_dir)
    save_invoice(
        InvoiceRow(number="A1/10/2026", issue_date=date(2026, 10, 1), total_net=Decimal("100"))
    )

    result = system.backup(output_dir=tmp_path / "out")
    assert result.verified

    blob = Fernet(key.encode()).decrypt(pathlib.Path(result.path).read_bytes())
    restore = tmp_path / "restore"
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        tar.extractall(restore, filter="data")
    with closing(sqlite3.connect(restore / "jdg_ksiegowy.db")) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT count(*) FROM invoice_items").fetchone()[0] == 1
        assert conn.execute("SELECT total_net FROM invoices").fetchone()[0] == 10000
    assert (restore / "faktury" / "f.xml").read_text(encoding="utf-8") == "<x/>"


def test_backup_requires_key(isolated_db, monkeypatch, tmp_path):
    from jdg_ksiegowy.config import settings

    monkeypatch.setattr(settings, "backup_key", "")
    with pytest.raises(ConfigMissingError, match="BACKUP_KEY"):
        system.backup(output_dir=tmp_path)


def test_retention_keeps_recent_and_monthly(tmp_path):
    names = [
        f"jdg_backup_2026{m:02d}{d:02d}_120000.tar.gz.fernet"
        for m in (9, 10, 11)
        for d in (1, 15, 28)
    ]
    for n in names:
        (tmp_path / n).write_bytes(b"x")
    removed = system._purge(tmp_path, keep_days=2, keep_monthly=2)
    kept = sorted(p.name for p in tmp_path.iterdir())
    assert "jdg_backup_20261128_120000.tar.gz.fernet" in kept  # najnowsze
    assert "jdg_backup_20261001_120000.tar.gz.fernet" in kept  # pierwsza kopia miesiaca
    assert "jdg_backup_20260901_120000.tar.gz.fernet" not in kept  # poza retencja miesieczna
    assert len(removed) + len(kept) == len(names)
