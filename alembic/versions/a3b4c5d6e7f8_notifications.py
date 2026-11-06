"""notifications

Notification context (data, dedupe key, read date) and the Expo push tokens of each device.

Revision ID: a3b4c5d6e7f8
Revises: 9f80e7e7254a
Create Date: 2026-11-06 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a3b4c5d6e7f8"
down_revision: str | None = "9f80e7e7254a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("notifications", sa.Column("dedupe_key", sa.String(length=255), nullable=True))
    op.add_column(
        "notifications", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_notifications_user_created", "notifications", ["user_id", "created_at"]
    )
    op.create_index(
        "uq_notifications_user_dedupe_key",
        "notifications",
        ["user_id", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )

    op.create_table(
        "push_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index(op.f("ix_push_tokens_user_id"), "push_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_push_tokens_user_id"), table_name="push_tokens")
    op.drop_table("push_tokens")
    op.drop_index("uq_notifications_user_dedupe_key", table_name="notifications")
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_column("notifications", "read_at")
    op.drop_column("notifications", "dedupe_key")
    op.drop_column("notifications", "data")
