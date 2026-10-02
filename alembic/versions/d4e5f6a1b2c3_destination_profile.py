"""destination_profile

Destination presentation data served by the API (previously hard-coded in the web
client): cover image, short summary and country facts.

Revision ID: d4e5f6a1b2c3
Revises: c3d4e5f6a1b2
Create Date: 2026-09-30 00:00:01.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4e5f6a1b2c3"
down_revision: str | None = "c3d4e5f6a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("destinations", sa.Column("image_url", sa.String(length=500), nullable=True))
    op.add_column("destinations", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column(
        "destinations",
        sa.Column("facts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("destinations", "facts")
    op.drop_column("destinations", "summary")
    op.drop_column("destinations", "image_url")
