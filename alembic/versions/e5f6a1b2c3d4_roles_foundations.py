"""roles_foundations

Schema step (expand) of the roles model: account types and statuses on users, the
`institutions` table renamed to `organizations`, staff memberships, student enrollments and
destination country codes. Data is backfilled by the next migration; the legacy columns
(`users.role`, `users.institution_id`, `organizations.config`) are dropped by a later
contract migration once web and mobile have switched.

Revision ID: e5f6a1b2c3d4
Revises: d4e5f6a1b2c3
Create Date: 2026-11-02 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e5f6a1b2c3d4"
down_revision: str | None = "d4e5f6a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

account_type = postgresql.ENUM(
    "student", "org_staff", "platform_admin", name="account_type", create_type=False
)
user_status = postgresql.ENUM(
    "active", "suspended", "pending_deletion", name="user_status", create_type=False
)
organization_status = postgresql.ENUM(
    "active", "suspended", "archived", name="organization_status", create_type=False
)
org_role = postgresql.ENUM("manager", "advisor", name="org_role", create_type=False)
enrollment_status = postgresql.ENUM(
    "active", "left", "revoked", name="enrollment_status", create_type=False
)
enrollment_source = postgresql.ENUM(
    "invitation",
    "csv_import",
    "join_code",
    "admin",
    "migration",
    name="enrollment_source",
    create_type=False,
)
ENUMS = (
    account_type,
    user_status,
    organization_status,
    org_role,
    enrollment_status,
    enrollment_source,
)


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
    for enum in ENUMS:
        enum.create(bind, checkfirst=True)

    # users
    op.add_column(
        "users",
        sa.Column("account_type", account_type, server_default="student", nullable=False),
    )
    op.add_column(
        "users", sa.Column("status", user_status, server_default="active", nullable=False)
    )
    op.add_column("users", sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("suspended_reason", sa.Text(), nullable=True))
    op.add_column(
        "users", sa.Column("deletion_scheduled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("mfa_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("users", sa.Column("mfa_secret", sa.Text(), nullable=True))
    op.add_column(
        "users", sa.Column("token_version", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    # The ORM no longer writes the legacy column: new rows get the default.
    op.alter_column("users", "role", server_default="student")

    # institutions -> organizations
    op.rename_table("institutions", "organizations")
    op.execute("ALTER INDEX institutions_pkey RENAME TO organizations_pkey")
    op.add_column("organizations", sa.Column("slug", sa.String(length=100), nullable=True))
    op.add_column(
        "organizations",
        sa.Column(
            "branding",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "organizations",
        sa.Column("status", organization_status, server_default="active", nullable=False),
    )
    op.add_column("organizations", sa.Column("join_code", sa.String(length=16), nullable=True))
    op.add_column("organizations", sa.Column("created_by", sa.UUID(), nullable=True))
    for column in _timestamps():
        op.add_column("organizations", column)
    op.create_unique_constraint("organizations_slug_key", "organizations", ["slug"])
    op.create_unique_constraint("organizations_join_code_key", "organizations", ["join_code"])
    op.create_foreign_key(
        "organizations_created_by_fkey",
        "organizations",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )

    # organization_members
    op.create_table(
        "organization_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("org_role", org_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        op.f("ix_organization_members_organization_id"),
        "organization_members",
        ["organization_id"],
    )

    # student_enrollments
    op.create_table(
        "student_enrollments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("status", enrollment_status, server_default="active", nullable=False),
        sa.Column("source", enrollment_source, nullable=False),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_by", sa.UUID(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ended_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_student_enrollments_organization_id"),
        "student_enrollments",
        ["organization_id"],
    )
    op.create_index(
        op.f("ix_student_enrollments_student_id"), "student_enrollments", ["student_id"]
    )
    op.create_index(
        "uq_student_enrollments_one_active",
        "student_enrollments",
        ["student_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    # destinations
    op.add_column("destinations", sa.Column("country_code", sa.String(length=2), nullable=True))
    op.create_index(op.f("ix_destinations_country_code"), "destinations", ["country_code"])


def downgrade() -> None:
    op.drop_index(op.f("ix_destinations_country_code"), table_name="destinations")
    op.drop_column("destinations", "country_code")

    op.drop_index("uq_student_enrollments_one_active", table_name="student_enrollments")
    op.drop_index(op.f("ix_student_enrollments_student_id"), table_name="student_enrollments")
    op.drop_index(
        op.f("ix_student_enrollments_organization_id"), table_name="student_enrollments"
    )
    op.drop_table("student_enrollments")

    op.drop_index(
        op.f("ix_organization_members_organization_id"), table_name="organization_members"
    )
    op.drop_table("organization_members")

    op.drop_constraint("organizations_created_by_fkey", "organizations", type_="foreignkey")
    op.drop_constraint("organizations_join_code_key", "organizations", type_="unique")
    op.drop_constraint("organizations_slug_key", "organizations", type_="unique")
    for column in (
        "updated_at",
        "created_at",
        "created_by",
        "join_code",
        "status",
        "settings",
        "branding",
        "slug",
    ):
        op.drop_column("organizations", column)
    op.execute("ALTER INDEX organizations_pkey RENAME TO institutions_pkey")
    op.rename_table("organizations", "institutions")

    op.alter_column("users", "role", server_default=None)
    for column in (
        "updated_at",
        "last_login_at",
        "token_version",
        "mfa_secret",
        "mfa_enabled",
        "deletion_scheduled_at",
        "suspended_reason",
        "suspended_at",
        "status",
        "account_type",
    ):
        op.drop_column("users", column)

    bind = op.get_bind()
    for enum in reversed(ENUMS):
        enum.drop(bind, checkfirst=True)
