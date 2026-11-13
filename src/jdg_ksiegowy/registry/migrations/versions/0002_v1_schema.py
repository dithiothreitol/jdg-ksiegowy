"""Schemat 1.0: pozycje faktur, numer KSeF, kwoty w groszach, filings, audit_log.

- `invoice_items`: pozycje faktur. Dla istniejacych faktur odtwarzane z pliku
  FA(3) (gdy jest dostepny i sumy sie zgadzaja), inaczej jedna pozycja z sum.
- `invoices`: rodzaj (VAT/KOR), okres rozliczeniowy, kraj i VAT-UE nabywcy,
  `ksef_number` (prawdziwy numer KSeF) obok `ksef_reference` (numer wysylki),
  data przyjecia i UPO, dane korekty; kolumna `vat_rate` przechodzi do pozycji.
- Kwoty i stawki we wszystkich tabelach: INTEGER w setnych (grosze / setne %).
- `filings` (zlozone deklaracje) i `audit_log` (dziennik czynnosci).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-13
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import sqlalchemy as sa
from alembic import context, op
from lxml import etree

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_MONEY = sa.Numeric(10, 2)
_RATE = sa.Numeric(5, 2)
_CENT = Decimal("0.01")

# tabela -> kolumny przechodzace z Numeric na INTEGER x100
_SCALED: dict[str, list[tuple[str, sa.types.TypeEngine, bool]]] = {
    "invoices": [("total_net", _MONEY, False), ("total_vat", _MONEY, False),
                 ("total_gross", _MONEY, False)],
    "expenses": [("total_net", _MONEY, False), ("total_vat", _MONEY, False),
                 ("total_gross", _MONEY, False), ("vat_rate", _RATE, True),
                 ("vat_deduction_pct", _RATE, False)],
    "contracts": [("net_amount", _MONEY, False), ("vat_rate", _RATE, True)],
    "buyers": [("default_vat_rate", _RATE, True)],
    "tax_payments": [("amount", _MONEY, False)],
}  # fmt: skip


def _dec(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _cents(value: Decimal) -> int:
    return int(value.quantize(_CENT, rounding=ROUND_HALF_UP) * 100)


def _resolve(path_str: str | None, data_dir: Path | None) -> Path | None:
    """Sciezka XML z rejestru moze pochodzic z innej maszyny — szukaj tez w data_dir."""
    if not path_str:
        return None
    if (direct := Path(path_str)).exists():
        return direct
    parts = (PureWindowsPath if "\\" in path_str else PurePosixPath)(path_str).parts
    if data_dir is not None and "faktury" in parts:
        candidate = Path(data_dir).joinpath(*parts[parts.index("faktury") :])
        if candidate.exists():
            return candidate
    return None


def _items_from_xml(
    path: Path, total_net: Decimal, total_vat: Decimal
) -> list[dict[str, Any]] | None:
    """Pozycje z FaWiersz FA(3); None gdy plik nieczytelny albo sumy sie nie zgadzaja."""
    try:
        rows = etree.parse(str(path)).getroot().findall(".//{*}FaWiersz")
        items: list[dict[str, Any]] = []
        for pos, row in enumerate(rows, start=1):
            rate = Decimal(row.findtext("{*}P_12") or "")
            qty = Decimal(row.findtext("{*}P_8B") or "1")
            price = Decimal(row.findtext("{*}P_9A") or "")
            net = (qty * price).quantize(_CENT, rounding=ROUND_HALF_UP)
            vat = (net * rate / 100).quantize(_CENT, rounding=ROUND_HALF_UP)
            items.append(
                {
                    "position": pos,
                    "description": row.findtext("{*}P_7") or "",
                    "quantity": str(qty),
                    "unit": row.findtext("{*}P_8A") or "usl.",
                    "unit_price_net": str(price),
                    "vat_rate": _cents(rate),
                    "net": _cents(net),
                    "vat": _cents(vat),
                    "gross": _cents(net + vat),
                }
            )
    except (OSError, etree.XMLSyntaxError, InvalidOperation):
        return None
    if not items:
        return None
    if sum(i["net"] for i in items) != _cents(total_net):
        return None
    if sum(i["vat"] for i in items) != _cents(total_vat):
        return None
    return items


def _fallback_item(row: sa.RowMapping) -> dict[str, Any]:
    net, vat = _dec(row["total_net"]), _dec(row["total_vat"])
    return {
        "position": 1,
        "description": "(pozycja odtworzona z sum rejestru)",
        "quantity": "1",
        "unit": "usl.",
        "unit_price_net": str(net.quantize(_CENT)),
        "vat_rate": _cents(_dec(row["vat_rate"] if row["vat_rate"] is not None else 23)),
        "net": _cents(net),
        "vat": _cents(vat),
        "gross": _cents(_dec(row["total_gross"])),
    }


def _create_items_table() -> sa.Table:
    return op.create_table(
        "invoice_items",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "invoice_id",
            sa.String,
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("quantity", sa.String, nullable=False),
        sa.Column("unit", sa.String, nullable=False),
        sa.Column("unit_price_net", sa.String, nullable=False),
        sa.Column("vat_rate", sa.Integer, nullable=False),
        sa.Column("vat_code", sa.String),
        sa.Column("gtu", sa.String),
        sa.Column("net", sa.Integer, nullable=False),
        sa.Column("vat", sa.Integer, nullable=False),
        sa.Column("gross", sa.Integer, nullable=False),
    )


def _legacy_items() -> list[dict[str, Any]]:
    """Pozycje odtworzone z faktur v0.2 — czytane PRZED skalowaniem kwot i usunieciem vat_rate."""
    bind = op.get_bind()
    data_dir = context.config.attributes.get("data_dir")
    rows = bind.execute(
        sa.text("SELECT id, total_net, total_vat, total_gross, vat_rate, xml_path FROM invoices")
    ).mappings()
    to_insert = []
    for row in rows:
        path = _resolve(row["xml_path"], data_dir)
        items = (
            _items_from_xml(path, _dec(row["total_net"]), _dec(row["total_vat"])) if path else None
        )
        for item in items or [_fallback_item(row)]:
            to_insert.append({**item, "invoice_id": row["id"]})
    return to_insert


def _scale_to_hundredths() -> None:
    for table, columns in _SCALED.items():
        for column, old_type, nullable in columns:
            op.execute(
                f"UPDATE {table} SET {column} = CAST(ROUND({column} * 100) AS INTEGER) "
                f"WHERE {column} IS NOT NULL"
            )
        with op.batch_alter_table(table) as batch:
            for column, old_type, nullable in columns:
                batch.alter_column(
                    column,
                    type_=sa.Integer(),
                    existing_type=old_type,
                    existing_nullable=nullable,
                )


def upgrade() -> None:
    # Pozycje tworzymy dopiero PO przebudowie tabeli `invoices` (batch = DROP + RENAME):
    # przy wlaczonych kluczach obcych DROP kaskadowo skasowalby juz wstawione pozycje.
    items = _legacy_items()  # przed skalowaniem — czyta kwoty w PLN i stara kolumne vat_rate
    _scale_to_hundredths()

    with op.batch_alter_table("invoices") as batch:
        batch.add_column(sa.Column("kind", sa.String, nullable=False, server_default="VAT"))
        batch.add_column(sa.Column("period_from", sa.Date))
        batch.add_column(sa.Column("period_to", sa.Date))
        batch.add_column(sa.Column("buyer_country", sa.String, nullable=False, server_default="PL"))
        batch.add_column(sa.Column("buyer_eu_vat", sa.String))
        batch.add_column(sa.Column("buyer_email", sa.String))
        batch.add_column(sa.Column("ksef_number", sa.String))
        batch.add_column(sa.Column("ksef_acquired_at", sa.DateTime))
        batch.add_column(sa.Column("ksef_upo_path", sa.String))
        batch.add_column(sa.Column("notes", sa.Text))
        batch.add_column(sa.Column("corrected_number", sa.String))
        batch.add_column(sa.Column("corrected_ksef_number", sa.String))
        batch.add_column(sa.Column("correction_reason", sa.Text))
        batch.drop_column("vat_rate")
        batch.create_index("ix_invoices_ksef_number", ["ksef_number"])

    items_table = _create_items_table()
    if items:
        op.bulk_insert(items_table, items)

    op.create_table(
        "filings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("form", sa.String, nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("month", sa.Integer),
        sa.Column("purpose", sa.Integer, nullable=False),
        sa.Column("file_path", sa.String, nullable=False),
        sa.Column("sha256", sa.String, nullable=False),
        sa.Column("env", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("reference_number", sa.String, index=True),
        sa.Column("status_code", sa.Integer),
        sa.Column("upo_path", sa.String),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("submitted_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )
    op.create_index("ix_filings_period", "filings", ["form", "year", "month"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime, nullable=False, index=True),
        sa.Column("actor", sa.String, nullable=False),
        sa.Column("action", sa.String, nullable=False),
        sa.Column("target", sa.String),
        sa.Column("outcome", sa.String, nullable=False),
        sa.Column("detail", sa.Text),
    )


def downgrade() -> None:
    raise NotImplementedError("Migracja 0002 jest jednokierunkowa — odtworz baze z backupu.")
