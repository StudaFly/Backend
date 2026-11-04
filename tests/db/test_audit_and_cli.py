"""Audit log (append-only, no secrets nor personal data) and the platform admin CLI."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from src.app import cli
from src.app.models.audit_log import AuditLog
from src.app.models.enums import AccountType
from src.app.models.user import User
from src.app.services import audit_service

from tests.db.conftest import TEST_DATABASE_URL, _database_url, make_engine, run, truncate_all
from tests.db.factories import (
    auth_headers,
    make_destination,
    make_enrollment,
    make_member,
    make_mobility,
    make_organization,
    make_platform_admin,
    make_user,
)


def test_scrub_drops_secrets_and_personal_data():
    changes = {
        "status": ["active", "suspended"],
        "password_hash": "x",
        "mfa_secret": "x",
        "email": "a@b.c",
        "nested": {"token": "x", "kept": 1},
    }

    assert audit_service.scrub(changes) == {
        "status": ["active", "suspended"],
        "nested": {"kept": 1},
    }


async def test_audit_log_is_read_only_through_the_api(api, db):
    admin = await make_platform_admin(db)
    await db.commit()
    headers = auth_headers(admin, mfa=True)

    for method in ("post", "patch", "put", "delete"):
        response = await api.request(method, "/admin/audit-logs", headers=headers)
        assert response.status_code == 405, method


async def test_audit_log_filters(api, db):
    admin = await make_platform_admin(db)
    organization = await make_organization(db)
    student = await make_user(db)
    await db.commit()
    headers = auth_headers(admin, mfa=True)
    await api.post(f"/admin/users/{student.id}/suspend", json={"reason": "Spam"}, headers=headers)
    await api.patch(f"/admin/organizations/{organization.id}", json={"name": "X"}, headers=headers)

    by_org = await api.get(f"/admin/audit-logs?organizationId={organization.id}", headers=headers)
    by_action = await api.get("/admin/audit-logs?action=user.suspend", headers=headers)

    assert [e["action"] for e in by_org.json()["data"]] == ["organization.update"]
    [entry] = by_action.json()["data"]
    assert entry["actorId"] == str(admin.id)
    assert entry["actorAccountType"] == "platform_admin"
    assert entry["targetId"] == str(student.id)
    assert "Spam" not in str(entry["changes"])
    assert entry["ip"]


@pytest.fixture
def cli_database(fake_cache, monkeypatch):
    with _database_url(TEST_DATABASE_URL):
        yield monkeypatch
    run(truncate_all())


async def _user(email: str) -> User | None:
    engine = make_engine()
    try:
        async with engine.connect() as conn:
            return (await conn.execute(select(User).where(User.email == email))).first()
    finally:
        await engine.dispose()


async def _audit_actions() -> list[str]:
    engine = make_engine()
    try:
        async with engine.connect() as conn:
            return list(await conn.scalars(select(AuditLog.action).order_by(AuditLog.created_at)))
    finally:
        await engine.dispose()


def test_cli_creates_then_revokes_a_platform_admin(cli_database, capsys):
    cli_database.setattr(cli.getpass, "getpass", lambda prompt: "founder-pass-1")

    cli.main(["create-platform-admin", "--email", "founder@studafly.com", "--name", "Founder"])
    created = run(_user("founder@studafly.com"))
    cli.main(["create-platform-admin", "--email", "founder@studafly.com"])
    cli.main(["revoke-platform-admin", "--email", "founder@studafly.com"])
    revoked = run(_user("founder@studafly.com"))

    assert created.account_type == AccountType.PLATFORM_ADMIN
    assert created.mfa_enabled is False
    assert created.password_hash
    assert "already a platform admin" in capsys.readouterr().out
    assert revoked.account_type == AccountType.STUDENT
    assert revoked.token_version == created.token_version + 1
    assert run(_audit_actions()) == ["platform_admin.grant", "platform_admin.revoke"]


def test_cli_refuses_to_promote_accounts_with_data(cli_database):
    async def seed():
        engine = make_engine()
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                organization = await make_organization(db)
                await make_member(
                    db,
                    organization,
                    user=await make_user(db, AccountType.ORG_STAFF, email="staff@example.com"),
                )
                await make_enrollment(
                    db, organization, await make_user(db, email="enrolled@example.com")
                )
                await make_mobility(
                    db,
                    await make_user(db, email="traveller@example.com"),
                    await make_destination(db),
                )
                await db.commit()
        finally:
            await engine.dispose()

    run(seed())

    for email in ("staff@example.com", "enrolled@example.com", "traveller@example.com"):
        with pytest.raises(SystemExit, match="Error:"):
            cli.main(["create-platform-admin", "--email", email])
        assert run(_user(email)).account_type != AccountType.PLATFORM_ADMIN


def test_cli_revoke_unknown_admin(cli_database):
    with pytest.raises(SystemExit, match="No platform admin"):
        cli.main(["revoke-platform-admin", "--email", "nobody@example.com"])
