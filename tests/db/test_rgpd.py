"""Right to erasure (scheduled deletion then purge), data export and retention jobs."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from src.app import cli
from src.app.models.audit_log import AuditLog
from src.app.models.document import Document
from src.app.models.enums import InvitationKind, InvitationStatus, OrgRole, UserStatus
from src.app.models.invitation import Invitation
from src.app.models.mobility import Mobility
from src.app.models.student_note import StudentNote
from src.app.models.task import Task
from src.app.models.user import User
from src.app.services import account_service, premium_service

from tests.db.conftest import TEST_DATABASE_URL, _database_url, run, truncate_all
from tests.db.factories import (
    PASSWORD,
    auth_headers,
    make_member,
    make_organization,
    make_platform_admin,
    make_user,
)


async def test_deleting_my_account_schedules_the_purge(api, db):
    student = await make_user(db)
    await db.commit()
    headers = auth_headers(student)

    deleted = await api.delete("/users/me", headers=headers)

    assert deleted.status_code == 204
    await db.refresh(student)
    assert student.status == UserStatus.PENDING_DELETION
    assert student.deletion_scheduled_at - datetime.now(UTC) > timedelta(days=29)
    assert (await api.get("/users/me", headers=headers)).status_code == 401
    login = await api.post("/auth/login", json={"email": student.email, "password": PASSWORD})
    assert login.json()["error"]["code"] == "ACCOUNT_PENDING_DELETION"


async def test_the_last_manager_cannot_delete_their_account(api, db):
    member = await make_member(db, await make_organization(db), OrgRole.MANAGER)
    await db.commit()

    response = await api.delete(
        "/users/me", headers=auth_headers(await db.get(User, member.user_id))
    )

    assert response.json()["error"]["code"] == "LAST_MANAGER"


async def test_platform_admins_are_removed_with_the_cli(api, db):
    admin = await make_platform_admin(db)
    await db.commit()

    assert (await api.delete("/users/me", headers=auth_headers(admin))).status_code == 403


async def _due_student(db, school):
    student = school.students["madrid"]
    db.add(StudentNote(organization_id=school.organization.id, student_id=student.id, body="Note"))
    db.add(
        Task(mobility_id=school.mobilities["madrid"].id, title="Visa", category="admin", priority=1)
    )
    db.add(
        Invitation(
            organization_id=school.organization.id,
            email=student.email,
            kind=InvitationKind.STUDENT,
            token_hash="a" * 64,
            expires_at=datetime.now(UTC),
            status=InvitationStatus.ACCEPTED,
        )
    )
    await db.commit()
    await premium_service.record_purchase(db, student, "pi_purge")
    student.status = UserStatus.PENDING_DELETION
    student.deletion_scheduled_at = datetime.now(UTC) - timedelta(minutes=1)
    await db.commit()
    return student


async def _count(db, model, *where) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(*where))


async def test_the_purge_removes_every_personal_data(db, school):
    student = await _due_student(db, school)
    student_id, email = student.id, student.email
    not_due = school.students["tokyo"]
    not_due.status = UserStatus.PENDING_DELETION
    not_due.deletion_scheduled_at = datetime.now(UTC) + timedelta(days=3)
    await db.commit()
    not_due_id = not_due.id
    audited_before = await _count(db, AuditLog, AuditLog.target_id == student_id)

    report = await account_service.purge_due_accounts(db)

    db.expire_all()
    assert (report.purged, report.skipped) == (1, [])
    assert await db.get(User, student_id) is None
    assert await db.get(User, not_due_id) is not None
    assert await _count(db, Mobility, Mobility.user_id == student_id) == 0
    assert await _count(db, StudentNote, StudentNote.student_id == student_id) == 0
    assert await _count(db, Invitation, Invitation.email == email) == 0
    assert await _count(db, AuditLog, AuditLog.target_id == student_id) == audited_before + 1
    entry = await db.scalar(select(AuditLog).where(AuditLog.action == "user.purge"))
    assert email not in str(entry.changes)


async def test_files_that_cannot_be_deleted_block_the_purge(db, school):
    student = await _due_student(db, school)
    student_id = student.id
    db.add(
        Document(mobility_id=school.mobilities["madrid"].id, file_url="s3://bucket/passport.pdf")
    )
    await db.commit()

    report = await account_service.purge_due_accounts(db)

    assert report.purged == 0
    assert report.skipped == [f"{student_id}: STORAGE_UNAVAILABLE"]
    db.expire_all()
    assert await db.get(User, student_id) is not None


async def test_the_purge_never_removes_the_last_manager(db):
    member = await make_member(db, await make_organization(db), OrgRole.MANAGER)
    manager = await db.get(User, member.user_id)
    manager.status = UserStatus.PENDING_DELETION
    manager.deletion_scheduled_at = datetime.now(UTC) - timedelta(days=1)
    manager_id = manager.id
    await db.commit()

    report = await account_service.purge_due_accounts(db)

    assert report.skipped == [f"{manager_id}: LAST_MANAGER"]


async def test_audit_logs_are_kept_one_year(db):
    db.add(
        AuditLog(
            actor_account_type="cli",
            action="old",
            target_type="user",
            created_at=datetime.now(UTC) - timedelta(days=400),
        )
    )
    db.add(AuditLog(actor_account_type="cli", action="recent", target_type="user"))
    await db.commit()

    assert await account_service.purge_audit_logs(db) == 1
    assert list(await db.scalars(select(AuditLog.action))) == ["recent"]


async def test_pending_invitations_expire(db):
    organization = await make_organization(db)
    for days in (-1, 1):
        db.add(
            Invitation(
                organization_id=organization.id,
                email=f"in-{days}@example.com",
                kind=InvitationKind.STUDENT,
                token_hash=str(days).rjust(64, "0"),
                expires_at=datetime.now(UTC) + timedelta(days=days),
            )
        )
    await db.commit()

    assert await account_service.expire_invitations(db) == 1


async def test_export_contains_my_data_and_no_secret(api, db, school):
    student = school.students["madrid"]
    db.add(
        StudentNote(organization_id=school.organization.id, student_id=student.id, body="Visa ok")
    )
    db.add(
        Task(mobility_id=school.mobilities["madrid"].id, title="Visa", category="admin", priority=1)
    )
    await db.commit()

    response = await api.get("/users/me/export", headers=auth_headers(student))

    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    data = response.json()
    assert data["profile"]["email"] == student.email
    assert data["mobilities"][0]["tasks"][0]["title"] == "Visa"
    assert data["notes_written_about_you"] == [
        {
            "organization": "École Démo",
            "body": "Visa ok",
            "created_at": data["notes_written_about_you"][0]["created_at"],
        }
    ]
    assert data["organizations"][0]["status"] == "active"
    for secret in ("password", "mfa_secret", "token_hash"):
        assert secret not in response.text


def test_the_maintenance_command_runs_every_job(fake_cache, capsys):
    with _database_url(TEST_DATABASE_URL):
        cli.main(["maintenance"])
    run(truncate_all())

    output = capsys.readouterr().out
    for job in ("expired_contracts", "expired_invitations", "purged_accounts", "purged_audit_logs"):
        assert f"{job}:" in output
