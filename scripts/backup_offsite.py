#!/usr/bin/env python3
"""Off-site backup całego stanu rozliczeń — szyfrowany tar.gz do OneDrive.

Pakuje: SQLite DB + UPO + XML faktur (FA(3)) + JPK + cert MF + DRA ZUS.
Pomija: backups/ (żeby nie spiralować), xsd/, infographics/.

Szyfrowanie: Fernet (AES-128-CBC + HMAC-SHA256). Klucz z env BACKUP_KEY
(wygeneruj: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())").

Retencja: ostatnie N codziennych + pierwsze z każdego miesiąca przez M miesięcy.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import tarfile
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

INCLUDE = ("jdg_ksiegowy.db", "upo", "faktury", "jpk", "mf_cert", "zus")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = REPO_ROOT / "data"
load_dotenv(REPO_ROOT / ".env")


def _default_output_dir() -> Path:
    """Auto-detect OneDrive, fallback do ~/Documents/jdg-ksiegowy-backups."""
    onedrive = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer")
    if onedrive and Path(onedrive).is_dir():
        return Path(onedrive) / "Backups" / "jdg-ksiegowy"
    return Path.home() / "Documents" / "jdg-ksiegowy-backups"


def _build_archive(data_dir: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in INCLUDE:
            src = data_dir / name
            if src.exists():
                tar.add(src, arcname=name)
    return buf.getvalue()


def _purge(out_dir: Path, keep_days: int, keep_monthly: int) -> list[Path]:
    """Zachowaj: ostatnie keep_days codziennych + 1-szy z każdego miesiąca (keep_monthly mies.).

    Reszta — usuń. Zwraca listę usuniętych.
    """
    files = sorted(out_dir.glob("jdg_backup_*.tar.gz.fernet"), reverse=True)
    if not files:
        return []
    keep: set[Path] = set(files[:keep_days])
    seen_months: set[str] = set()
    for f in files:
        ts = f.name.removeprefix("jdg_backup_").split("_")[0]  # YYYYMMDD
        month_key = ts[:6]
        if month_key not in seen_months:
            seen_months.add(month_key)
            keep.add(f)
            if len(seen_months) >= keep_monthly:
                break
    removed = []
    for f in files:
        if f not in keep:
            f.unlink()
            removed.append(f)
    return removed


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    p.add_argument("--output-dir", type=Path, default=None,
                   help="Domyślnie: OneDrive/Backups/jdg-ksiegowy lub ~/Documents/jdg-ksiegowy-backups")
    p.add_argument("--keep-days", type=int, default=30)
    p.add_argument("--keep-monthly", type=int, default=12)
    p.add_argument("--verify", action="store_true", help="Po zapisie odczytaj i sprawdź deszyfrowanie")
    args = p.parse_args()

    key = os.environ.get("BACKUP_KEY", "").strip()
    if not key:
        print("ERROR: brak BACKUP_KEY w env. Wygeneruj:", file=sys.stderr)
        print('  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"',
              file=sys.stderr)
        print("i dopisz do .env (oraz ZAPISZ w password managerze — bez klucza backupy nieodzyskiwalne).",
              file=sys.stderr)
        return 2

    try:
        fernet = Fernet(key.encode())
    except (ValueError, InvalidToken) as e:
        print(f"ERROR: nieprawidłowy BACKUP_KEY ({e})", file=sys.stderr)
        return 2

    data_dir = args.data_dir.resolve()
    if not data_dir.is_dir():
        print(f"ERROR: data-dir nie istnieje: {data_dir}", file=sys.stderr)
        return 2

    out_dir = (args.output_dir or _default_output_dir()).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    archive = _build_archive(data_dir)
    encrypted = fernet.encrypt(archive)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"jdg_backup_{ts}.tar.gz.fernet"
    out_file.write_bytes(encrypted)

    if args.verify:
        decrypted = fernet.decrypt(out_file.read_bytes())
        assert decrypted == archive, "Deszyfracja zwróciła inne bajty niż oryginał"

    removed = _purge(out_dir, args.keep_days, args.keep_monthly)

    print(f"OK: {out_file} ({len(encrypted):,} B, plain {len(archive):,} B)")
    if removed:
        print(f"Usunięto {len(removed)} starych kopii (retencja {args.keep_days}d + {args.keep_monthly}m)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
