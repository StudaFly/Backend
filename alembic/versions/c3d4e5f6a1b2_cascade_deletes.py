"""cascade_deletes

Deleting a mobility removes its tasks and documents; deleting a user removes
their mobilities and notifications (RGPD right to erasure).

Revision ID: c3d4e5f6a1b2
Revises: b2c3d4e5f6a1
Create Date: 2026-09-30 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

revision: str = "c3d4e5f6a1b2"
down_revision: str | None = "b2c3d4e5f6a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, column, referred table) — constraint names are PostgreSQL defaults
# from the initial schema (unnamed FKs → "<table>_<column>_fkey").
_CASCADE_FKS = [
    ("tasks", "mobility_id", "mobilities"),
    ("documents", "mobility_id", "mobilities"),
    ("mobilities", "user_id", "users"),
    ("notifications", "user_id", "users"),
]


def _recreate(ondelete: str | None) -> None:
    for table, column, referred in _CASCADE_FKS:
        name = f"{table}_{column}_fkey"
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, referred, [column], ["id"], ondelete=ondelete)


def upgrade() -> None:
    _recreate("CASCADE")


def downgrade() -> None:
    _recreate(None)
