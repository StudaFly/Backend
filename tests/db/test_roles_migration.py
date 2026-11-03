"""Roles migrations on a database filled with the legacy model (§13 of the roles spec):
upgrade, then downgrade back to the legacy schema."""

import json
import uuid

import pytest
from sqlalchemy import text

from tests.db.conftest import alembic, make_engine, run, truncate_all

LEGACY_REVISION = "d4e5f6a1b2c3"

SCHOOL_ID = uuid.uuid4()
OTHER_SCHOOL_ID = uuid.uuid4()
MANAGER_ID = uuid.uuid4()
ENROLLED_ID = uuid.uuid4()
INDEPENDENT_ID = uuid.uuid4()


async def _execute(*statements: tuple[str, dict]) -> None:
    engine = make_engine()
    try:
        async with engine.begin() as conn:
            for sql, params in statements:
                await conn.execute(text(sql), params)
    finally:
        await engine.dispose()


async def _fetch(sql: str, params: dict | None = None) -> list:
    engine = make_engine()
    try:
        async with engine.connect() as conn:
            return (await conn.execute(text(sql), params or {})).mappings().all()
    finally:
        await engine.dispose()


def _insert_user(user_id: uuid.UUID, role: str, institution_id: uuid.UUID | None) -> tuple:
    return (
        "INSERT INTO users (id, email, name, role, institution_id, is_premium, email_verified) "
        "VALUES (:id, :email, 'Legacy', :role, :inst, false, false)",
        {"id": user_id, "email": f"{user_id}@example.com", "role": role, "inst": institution_id},
    )


def _insert_school(school_id: uuid.UUID, name: str, config: dict) -> tuple:
    return (
        "INSERT INTO institutions (id, name, config) VALUES (:id, :name, CAST(:config AS jsonb))",
        {"id": school_id, "name": name, "config": json.dumps(config)},
    )


@pytest.fixture
def legacy_database():
    run(truncate_all())
    alembic("downgrade", LEGACY_REVISION)
    yield
    run(truncate_all())
    alembic("upgrade", "head")


def test_upgrade_converts_legacy_rows_and_downgrade_restores_them(legacy_database):
    config = {"primary_color": "#123456", "accent_color": "#654321", "ri_contact": {"name": "RI"}}
    run(
        _execute(
            _insert_school(SCHOOL_ID, "École Démo", config),
            _insert_school(OTHER_SCHOOL_ID, "Ecole Demo", {}),
            _insert_user(MANAGER_ID, "admin", SCHOOL_ID),
            _insert_user(ENROLLED_ID, "student", SCHOOL_ID),
            _insert_user(INDEPENDENT_ID, "student", None),
            (
                "INSERT INTO destinations (id, country, city) VALUES "
                "(gen_random_uuid(), 'République Tchèque', 'Prague'), "
                "(gen_random_uuid(), 'Atlantide', 'Poseidonis')",
                {},
            ),
        )
    )

    alembic("upgrade", "head")

    users = {
        row["id"]: row["account_type"]
        for row in run(_fetch("SELECT id, account_type::text FROM users"))
    }
    assert users == {MANAGER_ID: "org_staff", ENROLLED_ID: "student", INDEPENDENT_ID: "student"}

    members = run(
        _fetch(
            "SELECT organization_id, user_id, org_role::text, is_active FROM organization_members"
        )
    )
    assert [dict(m) for m in members] == [
        {
            "organization_id": SCHOOL_ID,
            "user_id": MANAGER_ID,
            "org_role": "manager",
            "is_active": True,
        }
    ]

    enrollments = run(
        _fetch(
            "SELECT organization_id, student_id, status::text, source::text FROM student_enrollments"
        )
    )
    assert [dict(e) for e in enrollments] == [
        {
            "organization_id": SCHOOL_ID,
            "student_id": ENROLLED_ID,
            "status": "active",
            "source": "migration",
        }
    ]

    schools = {
        row["id"]: row
        for row in run(_fetch("SELECT id, slug, join_code, branding, settings FROM organizations"))
    }
    assert schools[SCHOOL_ID]["branding"] == {"primary_color": "#123456", "accent_color": "#654321"}
    assert schools[SCHOOL_ID]["settings"] == {"ri_contact": {"name": "RI"}}
    # Same slug base for both schools: the second one gets a suffix.
    assert {s["slug"] for s in schools.values()} == {"ecole-demo", "ecole-demo-2"}
    codes = [s["join_code"] for s in schools.values()]
    assert len(set(codes)) == 2 and all(len(code) == 10 for code in codes)

    countries = {
        row["country"]: row["country_code"]
        for row in run(_fetch("SELECT country, country_code FROM destinations"))
    }
    assert countries == {"République Tchèque": "CZ", "Atlantide": None}

    alembic("downgrade", LEGACY_REVISION)

    legacy = {
        row["id"]: (row["role"], row["institution_id"])
        for row in run(_fetch("SELECT id, role, institution_id FROM users"))
    }
    assert legacy == {
        MANAGER_ID: ("admin", SCHOOL_ID),
        ENROLLED_ID: ("student", SCHOOL_ID),
        INDEPENDENT_ID: ("student", None),
    }
    restored = run(_fetch("SELECT config FROM institutions WHERE id = :id", {"id": SCHOOL_ID}))
    assert restored[0]["config"] == config


@pytest.mark.parametrize(
    ("role", "institution"), [("superadmin", None), ("admin", None)], ids=["superadmin", "orphan"]
)
def test_upgrade_refuses_accounts_needing_a_human_decision(legacy_database, role, institution):
    run(_execute(_insert_user(uuid.uuid4(), role, institution)))

    with pytest.raises(RuntimeError, match="cannot be converted automatically"):
        alembic("upgrade", "head")

    # The whole upgrade ran in one transaction: still on the legacy schema.
    tables = run(_fetch("SELECT to_regclass('institutions') AS legacy"))
    assert tables[0]["legacy"] == "institutions"
