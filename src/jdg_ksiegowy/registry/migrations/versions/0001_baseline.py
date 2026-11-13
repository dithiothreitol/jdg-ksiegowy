"""Schemat bazowy v0.2 (sprzed Alembica).

Dla nowej bazy tworzy tabele w ksztalcie v0.2. Dla istniejacej bazy bez
`alembic_version` dociaga poprawki, ktore dotad robil `init_db()` ad hoc
(vat_deductible -> vat_deduction_pct, ksef_number, reverse_charge). Dzieki temu
kazda baza — nowa i stara — przechodzi ta sama sciezka migracji do 1.0.

Revision ID: 0001
Revises:
Create Date: 2026-11-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

_MONEY = sa.Numeric(10, 2)
_RATE = sa.Numeric(5, 2)


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    existing = _tables()

    if "buyers" not in existing:
        op.create_table(
            "buyers",
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("name", sa.String, nullable=False),
            sa.Column("nip", sa.String, index=True),
            sa.Column("eu_vat_number", sa.String, index=True),
            sa.Column("address", sa.String),
            sa.Column("email", sa.String),
            sa.Column("country_code", sa.String),
            sa.Column("default_description", sa.String),
            sa.Column("default_vat_rate", _RATE),
            sa.Column("notes", sa.String),
            sa.Column("created_at", sa.DateTime),
            sa.Column("last_used_at", sa.DateTime),
        )

    if "invoices" not in existing:
        op.create_table(
            "invoices",
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("number", sa.String, nullable=False, unique=True),
            sa.Column("issue_date", sa.Date, nullable=False),
            sa.Column("sale_date", sa.Date, nullable=False),
            sa.Column("payment_due", sa.Date, nullable=False),
            sa.Column("buyer_name", sa.String, nullable=False),
            sa.Column("buyer_nip", sa.String, nullable=False),
            sa.Column("buyer_address", sa.String),
            sa.Column("total_net", _MONEY, nullable=False),
            sa.Column("total_vat", _MONEY, nullable=False),
            sa.Column("total_gross", _MONEY, nullable=False),
            sa.Column("vat_rate", _RATE),
            sa.Column("status", sa.String),
            sa.Column("ksef_reference", sa.String),
            sa.Column("ksef_sent_at", sa.DateTime),
            sa.Column("paid_at", sa.DateTime),
            sa.Column("docx_path", sa.String),
            sa.Column("xml_path", sa.String),
            sa.Column("created_at", sa.DateTime),
        )

    if "contracts" not in existing:
        op.create_table(
            "contracts",
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("buyer_name", sa.String, nullable=False),
            sa.Column("buyer_nip", sa.String, nullable=False),
            sa.Column("buyer_address", sa.String),
            sa.Column("buyer_email", sa.String),
            sa.Column("description", sa.String, nullable=False),
            sa.Column("net_amount", _MONEY, nullable=False),
            sa.Column("vat_rate", _RATE),
            sa.Column("cycle", sa.String),
            sa.Column("day_of_month", sa.Integer),
            sa.Column("auto_send_ksef", sa.Boolean),
            sa.Column("auto_send_email", sa.Boolean),
            sa.Column("active", sa.Boolean),
            sa.Column("created_at", sa.DateTime),
        )

    if "expenses" not in existing:
        op.create_table(
            "expenses",
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("seller_name", sa.String, nullable=False),
            sa.Column("seller_nip", sa.String, nullable=False),
            sa.Column("seller_country", sa.String),
            sa.Column("document_number", sa.String, nullable=False),
            sa.Column("issue_date", sa.Date, nullable=False),
            sa.Column("receive_date", sa.Date, nullable=False),
            sa.Column("description", sa.String),
            sa.Column("category", sa.String),
            sa.Column("total_net", _MONEY, nullable=False),
            sa.Column("total_vat", _MONEY, nullable=False),
            sa.Column("total_gross", _MONEY, nullable=False),
            sa.Column("vat_rate", _RATE),
            sa.Column("vat_deduction_pct", _RATE, nullable=False, server_default="100"),
            sa.Column("reverse_charge", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("file_path", sa.String),
            sa.Column("notes", sa.String),
            sa.Column("ksef_number", sa.String, index=True),
            sa.Column("created_at", sa.DateTime),
        )
    else:
        _legacy_expense_fixes()

    if "tax_payments" not in existing:
        op.create_table(
            "tax_payments",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("type", sa.String, nullable=False),
            sa.Column("month", sa.Integer, nullable=False),
            sa.Column("year", sa.Integer, nullable=False),
            sa.Column("amount", _MONEY, nullable=False),
            sa.Column("due_date", sa.Date, nullable=False),
            sa.Column("paid", sa.Boolean),
            sa.Column("paid_at", sa.DateTime),
            sa.Column("created_at", sa.DateTime),
        )


def _legacy_expense_fixes() -> None:
    """Poprawki z dawnego `init_db()` — idempotentne."""
    cols = _columns("expenses")
    if "vat_deductible" in cols:
        if "vat_deduction_pct" not in cols:
            op.add_column(
                "expenses",
                sa.Column("vat_deduction_pct", _RATE, nullable=False, server_default="100"),
            )
        op.execute(
            "UPDATE expenses SET vat_deduction_pct = CASE WHEN vat_deductible THEN 100 ELSE 0 END"
        )
        with op.batch_alter_table("expenses") as batch:
            batch.drop_column("vat_deductible")
    cols = _columns("expenses")
    if "ksef_number" not in cols:
        op.add_column("expenses", sa.Column("ksef_number", sa.String))
        op.create_index("ix_expenses_ksef_number", "expenses", ["ksef_number"])
    if "reverse_charge" not in cols:
        op.add_column(
            "expenses",
            sa.Column("reverse_charge", sa.Boolean, nullable=False, server_default="0"),
        )


def downgrade() -> None:
    for table in ("tax_payments", "expenses", "contracts", "invoices", "buyers"):
        op.drop_table(table)
