"""roles_constraints

Makes the organization slug and join code mandatory once the data migration has filled them.

Revision ID: a7b8c9d0e1f2
Revises: f6a1b2c3d4e5
Create Date: 2026-11-02 00:00:02.000000

"""
from collections.abc import Sequence

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("organizations", "slug", nullable=False)
    op.alter_column("organizations", "join_code", nullable=False)


def downgrade() -> None:
    op.alter_column("organizations", "join_code", nullable=True)
    op.alter_column("organizations", "slug", nullable=True)
