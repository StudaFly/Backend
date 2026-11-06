"""`users.is_premium` becomes admin grants (reason `migration`), and comes back on downgrade."""

import uuid

import pytest
from sqlalchemy import text

from tests.db.conftest import alembic, make_engine, run, truncate_all

BEFORE_PREMIUM = "c9d0e1f2a3b4"
INDEPENDENT, ENROLLED, FREE = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
SCHOOL = uuid.uuid4()


async def _execute(sql: str, params: dict | None = None) -> list:
    engine = make_engine()
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text(sql), params or {})
            return result.mappings().all() if result.returns_rows else []
    finally:
        await engine.dispose()


@pytest.fixture
def before_premium():
    run(truncate_all())
    alembic("downgrade", BEFORE_PREMIUM)
    yield
    run(truncate_all())
    alembic("upgrade", "head")


def test_is_premium_round_trip(before_premium):
    run(
        _execute(
            "INSERT INTO organizations (id, name, slug, join_code) VALUES (:id, 'S', 's', 'CODE')",
            {"id": SCHOOL},
        )
    )
    for user_id, premium in ((INDEPENDENT, True), (ENROLLED, True), (FREE, False)):
        run(
            _execute(
                "INSERT INTO users (id, email, name, is_premium, email_verified) "
                "VALUES (:id, :email, 'U', :premium, false)",
                {"id": user_id, "email": f"{user_id}@example.com", "premium": premium},
            )
        )
    run(
        _execute(
            "INSERT INTO student_enrollments (id, organization_id, student_id, source) "
            "VALUES (gen_random_uuid(), :org, :student, 'admin')",
            {"org": SCHOOL, "student": ENROLLED},
        )
    )

    alembic("upgrade", "head")

    grants = run(_execute("SELECT user_id, source::text, reason FROM premium_grants"))
    assert [dict(g) for g in grants] == [
        {"user_id": INDEPENDENT, "source": "admin_grant", "reason": "migration"}
    ]

    alembic("downgrade", BEFORE_PREMIUM)

    flags = {r["id"]: r["is_premium"] for r in run(_execute("SELECT id, is_premium FROM users"))}
    assert flags == {INDEPENDENT: True, ENROLLED: False, FREE: False}
