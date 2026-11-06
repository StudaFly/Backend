"""`/admin/users`: account creation, suspension, scheduled deletion, guarded targets."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from src.app.models.audit_log import AuditLog
from src.app.models.enums import AccountType, OrgRole, UserStatus
from src.app.models.organization_member import OrganizationMember
from src.app.models.user import User
from src.app.services import auth_service

from tests.db.factories import (
    PASSWORD,
    auth_headers,
    make_destination,
    make_member,
    make_mobility,
    make_organization,
    make_platform_admin,
    make_user,
)


@pytest.fixture
async def admin_headers(db):
    admin = await make_platform_admin(db)
    await db.commit()
    return auth_headers(admin, mfa=True)


async def _audit_actions(db, target_id) -> list[str]:
    return list(await db.scalars(select(AuditLog.action).where(AuditLog.target_id == target_id)))


@pytest.fixture
def setup_tokens(monkeypatch) -> list[str]:
    tokens: list[str] = []
    original = auth_service.send_password_setup

    async def capture(user):
        tokens.append(await original(user))
        return tokens[-1]

    monkeypatch.setattr(auth_service, "send_password_setup", capture)
    return tokens


async def test_create_a_student_who_then_sets_a_password(api, db, admin_headers, setup_tokens):
    response = await api.post(
        "/admin/users",
        json={"email": "lucas@example.com", "name": "Lucas", "accountType": "student"},
        headers=admin_headers,
    )

    assert response.status_code == 201, response.text
    user_id = response.json()["data"]["id"]
    assert await _audit_actions(db, user_id) == ["user.create"]
    [token] = setup_tokens

    reset = await api.post(
        "/auth/reset-password", json={"token": token, "newPassword": "new-pass-123"}
    )
    login = await api.post(
        "/auth/login", json={"email": "lucas@example.com", "password": "new-pass-123"}
    )
    replay = await api.post(
        "/auth/reset-password", json={"token": token, "newPassword": "other-pass-1"}
    )

    assert reset.status_code == 200
    assert login.status_code == 200
    assert replay.status_code == 404


async def test_create_a_staff_account_in_an_organization(api, db, admin_headers):
    organization = await make_organization(db)
    await db.commit()

    response = await api.post(
        "/admin/users",
        json={
            "email": "marie@example.com",
            "name": "Marie",
            "accountType": "org_staff",
            "organizationId": str(organization.id),
            "orgRole": "advisor",
        },
        headers=admin_headers,
    )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert (data["accountType"], data["orgRole"]) == ("org_staff", "advisor")
    assert data["organization"]["id"] == str(organization.id)


async def test_create_a_student_enrolled_in_an_organization(api, db, admin_headers):
    organization = await make_organization(db)
    await db.commit()

    response = await api.post(
        "/admin/users",
        json={
            "email": "eleve@example.com",
            "name": "Élève",
            "accountType": "student",
            "organizationId": str(organization.id),
        },
        headers=admin_headers,
    )

    assert response.status_code == 201, response.text
    assert response.json()["data"]["organization"]["id"] == str(organization.id)
    actions = await db.scalars(select(AuditLog.action).order_by(AuditLog.action))
    assert list(actions) == ["enrollment.create", "user.create"]


@pytest.mark.parametrize(
    "payload",
    [
        {"accountType": "platform_admin"},
        {"accountType": "org_staff"},
        {"accountType": "student", "orgRole": "manager"},
        {"accountType": "student", "role": "superadmin"},
    ],
    ids=["platform-admin", "staff-without-org", "student-with-role", "unknown-field"],
)
async def test_invalid_account_creation(api, admin_headers, payload):
    response = await api.post(
        "/admin/users",
        json={"email": "x@example.com", "name": "X", **payload},
        headers=admin_headers,
    )

    assert response.status_code == 422


async def test_account_type_cannot_be_changed_through_the_api(api, db, admin_headers):
    student = await make_user(db)
    await db.commit()

    response = await api.patch(
        f"/admin/users/{student.id}",
        json={"accountType": "platform_admin"},
        headers=admin_headers,
    )

    assert response.status_code == 422
    await db.refresh(student)
    assert student.account_type == AccountType.STUDENT


async def test_update_logs_field_names_but_no_personal_data(api, db, admin_headers):
    student = await make_user(db, name="Old Name")
    await db.commit()

    response = await api.patch(
        f"/admin/users/{student.id}",
        json={"name": "New Name", "email": "new@example.com"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    entry = await db.scalar(select(AuditLog).where(AuditLog.target_id == student.id))
    assert entry.changes == {"fields": ["email", "name"]}
    assert "New Name" not in str(entry.changes) and "new@example.com" not in str(entry.changes)


async def test_list_filters_and_paginates(api, db, admin_headers):
    organization = await make_organization(db)
    for i in range(3):
        await make_user(db, email=f"filter-{i}@example.com")
    await make_member(db, organization, OrgRole.ADVISOR)
    await db.commit()

    page = await api.get("/admin/users?q=filter-&perPage=2", headers=admin_headers)
    staff = await api.get("/admin/users?accountType=org_staff", headers=admin_headers)
    in_org = await api.get(f"/admin/users?organizationId={organization.id}", headers=admin_headers)

    assert (page.json()["total"], len(page.json()["data"])) == (3, 2)
    assert [u["accountType"] for u in staff.json()["data"]] == ["org_staff"]
    assert in_org.json()["total"] == 1


async def test_detail_lists_mobilities(api, db, admin_headers):
    student = await make_user(db)
    await make_mobility(db, student, await make_destination(db, city="Lisbonne"))
    await db.commit()

    response = await api.get(f"/admin/users/{student.id}", headers=admin_headers)

    assert [m["city"] for m in response.json()["data"]["mobilities"]] == ["Lisbonne"]


async def test_suspension_requires_a_reason_and_locks_the_account_out(api, db, admin_headers):
    student = await make_user(db)
    await db.commit()
    student_headers = auth_headers(student)

    no_reason = await api.post(f"/admin/users/{student.id}/suspend", json={}, headers=admin_headers)
    suspended = await api.post(
        f"/admin/users/{student.id}/suspend", json={"reason": "Fraud"}, headers=admin_headers
    )

    assert no_reason.status_code == 422
    assert suspended.status_code == 200
    assert suspended.json()["data"]["suspendedReason"] == "Fraud"
    assert (await api.get("/users/me", headers=student_headers)).status_code == 401
    login = await api.post("/auth/login", json={"email": student.email, "password": PASSWORD})
    assert login.json()["error"]["code"] == "ACCOUNT_SUSPENDED"

    reactivated = await api.post(f"/admin/users/{student.id}/reactivate", headers=admin_headers)
    assert reactivated.json()["data"]["status"] == "active"
    assert await _audit_actions(db, student.id) == ["user.suspend", "user.reactivate"]


async def test_deletion_is_scheduled_and_can_be_cancelled(api, db, admin_headers):
    student = await make_user(db)
    await db.commit()

    deleted = await api.delete(f"/admin/users/{student.id}", headers=admin_headers)

    data = deleted.json()["data"]
    assert data["status"] == "pending_deletion"
    scheduled = datetime.fromisoformat(data["deletionScheduledAt"])
    assert scheduled - datetime.now(UTC) > timedelta(days=29)
    login = await api.post("/auth/login", json={"email": student.email, "password": PASSWORD})
    assert login.json()["error"]["code"] == "ACCOUNT_PENDING_DELETION"

    cancelled = await api.post(f"/admin/users/{student.id}/reactivate", headers=admin_headers)
    assert cancelled.json()["data"]["deletionScheduledAt"] is None


async def test_the_last_manager_cannot_be_deleted(api, db, admin_headers):
    organization = await make_organization(db)
    member = await make_member(db, organization, OrgRole.MANAGER)
    await db.commit()

    response = await api.delete(f"/admin/users/{member.user_id}", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "LAST_MANAGER"
    assert (await db.get(User, member.user_id)).status == UserStatus.ACTIVE


async def test_a_manager_with_a_colleague_can_be_deleted(api, db, admin_headers):
    organization = await make_organization(db)
    member = await make_member(db, organization, OrgRole.MANAGER)
    await make_member(db, organization, OrgRole.MANAGER)
    await db.commit()

    response = await api.delete(f"/admin/users/{member.user_id}", headers=admin_headers)

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("patch", "", {"name": "X"}),
        ("post", "/suspend", {"reason": "Because"}),
        ("post", "/reactivate", None),
        ("delete", "", None),
    ],
)
async def test_platform_admins_are_managed_with_the_cli_only(
    api, db, admin_headers, method, suffix, body
):
    other = await make_platform_admin(db)
    await db.commit()

    response = await api.request(
        method, f"/admin/users/{other.id}{suffix}", json=body, headers=admin_headers
    )

    assert response.status_code == 403


async def test_overview_counts(api, db, admin_headers):
    await make_user(db)
    await make_user(db, status=UserStatus.SUSPENDED)
    await make_organization(db)
    await db.commit()

    data = (await api.get("/admin/overview", headers=admin_headers)).json()["data"]

    assert data["users"]["byAccountType"] == {"student": 2, "org_staff": 0, "platform_admin": 1}
    assert data["users"]["byStatus"]["suspended"] == 1
    assert data["organizations"] == {
        "total": 1,
        "byStatus": {"active": 1, "suspended": 0, "archived": 0},
    }


async def test_forgot_password_never_reveals_whether_an_account_exists(api, db, fake_cache):
    student = await make_user(db)
    await db.commit()

    known = await api.post("/auth/forgot-password", json={"email": student.email})
    unknown = await api.post("/auth/forgot-password", json={"email": "nobody@example.com"})

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert len([k for k in fake_cache if k.startswith("auth:password:")]) == 1


async def test_member_count_is_unaffected_by_staff_creation_failure(api, db, admin_headers):
    organization = await make_organization(db)
    await make_user(db, email="taken@example.com")
    await db.commit()

    response = await api.post(
        "/admin/users",
        json={
            "email": "taken@example.com",
            "name": "Dup",
            "accountType": "org_staff",
            "organizationId": str(organization.id),
            "orgRole": "advisor",
        },
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_TAKEN"
    assert not list(await db.scalars(select(OrganizationMember.id)))
