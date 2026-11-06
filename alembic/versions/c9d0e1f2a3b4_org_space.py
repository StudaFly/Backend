"""org_space

Invitations (students and staff), advisor perimeters by country, manual mobility
assignments and internal notes of the international relations staff.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-11-03 00:00:01.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

invitation_kind = postgresql.ENUM("student", "staff", name="invitation_kind", create_type=False)
invitation_status = postgresql.ENUM(
    "pending", "accepted", "revoked", "expired", name="invitation_status", create_type=False
)
org_role = postgresql.ENUM("manager", "advisor", name="org_role", create_type=False)


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
    invitation_kind.create(bind, checkfirst=True)
    invitation_status.create(bind, checkfirst=True)

    op.create_table(
        "invitations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("kind", invitation_kind, nullable=False),
        sa.Column("org_role", org_role, nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("from_csv", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", invitation_status, server_default="pending", nullable=False),
        sa.Column("invited_by", sa.UUID(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_invitations_organization_id"), "invitations", ["organization_id"])
    op.create_index(op.f("ix_invitations_email"), "invitations", ["email"])

    op.create_table(
        "advisor_perimeters",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["organization_members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "country_code"),
    )
    op.create_index(op.f("ix_advisor_perimeters_member_id"), "advisor_perimeters", ["member_id"])

    op.create_table(
        "mobility_advisor_overrides",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("mobility_id", sa.UUID(), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("set_by", sa.UUID(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["mobility_id"], ["mobilities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["organization_members.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["set_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mobility_id"),
    )
    op.create_index(
        op.f("ix_mobility_advisor_overrides_member_id"),
        "mobility_advisor_overrides",
        ["member_id"],
    )

    op.create_table(
        "student_notes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("author_member_id", sa.UUID(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["author_member_id"], ["organization_members.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_student_notes_student_id"), "student_notes", ["student_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_student_notes_student_id"), table_name="student_notes")
    op.drop_table("student_notes")
    op.drop_index(
        op.f("ix_mobility_advisor_overrides_member_id"), table_name="mobility_advisor_overrides"
    )
    op.drop_table("mobility_advisor_overrides")
    op.drop_index(op.f("ix_advisor_perimeters_member_id"), table_name="advisor_perimeters")
    op.drop_table("advisor_perimeters")
    op.drop_index(op.f("ix_invitations_email"), table_name="invitations")
    op.drop_index(op.f("ix_invitations_organization_id"), table_name="invitations")
    op.drop_table("invitations")

    bind = op.get_bind()
    invitation_status.drop(bind, checkfirst=True)
    invitation_kind.drop(bind, checkfirst=True)
