"""premium_data

`users.is_premium = true` without an active enrollment becomes an `admin_grant` with the
reason `migration`. Premium coming from an organization is now computed from its contract.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-11-03 00:00:03.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MIGRATION_REASON = "migration"


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "INSERT INTO premium_grants (id, user_id, source, reason) "
            "SELECT gen_random_uuid(), u.id, 'admin_grant', :reason FROM users u "
            "WHERE u.is_premium AND NOT EXISTS ("
            "  SELECT 1 FROM student_enrollments e "
            "  WHERE e.student_id = u.id AND e.status = 'active')"
        ),
        {"reason": MIGRATION_REASON},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE users SET is_premium = EXISTS ("
            "  SELECT 1 FROM premium_grants g WHERE g.user_id = users.id "
            "  AND g.revoked_at IS NULL AND g.starts_at <= now() "
            "  AND (g.ends_at IS NULL OR g.ends_at > now()))"
        )
    )
    conn.execute(
        sa.text(
            "DELETE FROM premium_grants WHERE source = 'admin_grant' AND reason = :reason"
        ),
        {"reason": MIGRATION_REASON},
    )
