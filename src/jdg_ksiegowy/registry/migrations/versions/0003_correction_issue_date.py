"""Data wystawienia faktury korygowanej (DataWystFaKorygowanej w FA(3)).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("corrected_issue_date", sa.Date))


def downgrade() -> None:
    with op.batch_alter_table("invoices") as batch:
        batch.drop_column("corrected_issue_date")
