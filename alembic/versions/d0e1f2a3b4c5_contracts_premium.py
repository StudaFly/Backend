"""contracts_premium

B2B contracts of the organizations and B2C Premium grants (purchase or admin grant).

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-11-03 00:00:02.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d0e1f2a3b4c5"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

contract_status = postgresql.ENUM(
    "pilot", "active", "expired", "suspended", "cancelled", name="contract_status", create_type=False
)
premium_source = postgresql.ENUM("purchase", "admin_grant", name="premium_source", create_type=False)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    contract_status.create(bind, checkfirst=True)
    premium_source.create(bind, checkfirst=True)

    op.create_table(
        "contracts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("plan", sa.String(length=50), nullable=False),
        sa.Column("status", contract_status, nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("price_cents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("currency", sa.CHAR(length=3), server_default="EUR", nullable=False),
        sa.Column("student_quota", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("end_date >= start_date", name="ck_contracts_dates"),
    )
    op.create_index(op.f("ix_contracts_organization_id"), "contracts", ["organization_id"])

    op.create_table(
        "premium_grants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("source", premium_source, nullable=False),
        sa.Column("stripe_payment_ref", sa.String(length=255), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.CHAR(length=3), nullable=True),
        sa.Column(
            "starts_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.UUID(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("granted_by", sa.UUID(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revoked_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["granted_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_payment_ref"),
    )
    op.create_index(op.f("ix_premium_grants_user_id"), "premium_grants", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_premium_grants_user_id"), table_name="premium_grants")
    op.drop_table("premium_grants")
    op.drop_index(op.f("ix_contracts_organization_id"), table_name="contracts")
    op.drop_table("contracts")
    bind = op.get_bind()
    premium_source.drop(bind, checkfirst=True)
    contract_status.drop(bind, checkfirst=True)
