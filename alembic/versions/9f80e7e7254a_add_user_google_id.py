"""add_user_google_id

Google sign-in: store the Google account identifier ("sub" claim) to find the user
again even if the email of the Google account changes.

Revision ID: 9f80e7e7254a
Revises: f2a3b4c5d6e7
Create Date: 2026-11-04 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9f80e7e7254a"
down_revision: str | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_id", sa.String(length=255), nullable=True))
    op.create_index(op.f("ix_users_google_id"), "users", ["google_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_google_id"), table_name="users")
    op.drop_column("users", "google_id")
