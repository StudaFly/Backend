"""drop_users_is_premium

Premium is computed from grants and contracts: the flag column goes away.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-11-03 00:00:04.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("users", "is_premium")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_premium", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
