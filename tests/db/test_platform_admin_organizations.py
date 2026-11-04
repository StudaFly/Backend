"""`/admin/organizations`: lifecycle, team (at least one active manager) and students."""

from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from src.app.authz import load_actor, require_org_role
from src.app.core.exceptions import ForbiddenError
from src.app.models.audit_log import AuditLog
from src.app.models.enums import AccountType, EnrollmentStatus, OrgRole
from src.app.models.organization_member import OrganizationMember
from src.app.models.student_enrollment import StudentEnrollment
from src.app.models.user import User

from tests.db.factories import (
    auth_headers,
    make_enrollment,
    make_member,
    make_organization,
    make_platform_admin,
    make_user,
)

GET_REQUEST = SimpleNamespace(method="GET")


@pytest.fixture
async def admin_headers(db):
    admin = await make_platform_admin(db)
    await db.commit()
    return auth_headers(admin, mfa=True)


async def _audit_count(db) -> int:
    return await db.scalar(select(func.count(AuditLog.id)))


async def test_create_an_organization_with_its_first_manager(api, db, admin_headers):
    response = await api.post(
        "/admin/organizations",
        json={
            "name": "École Démo",
            "branding": {"primary_color": "#213458"},
            "manager": {"email": "ri@ecole-demo.fr", "name": "Marie"},
        },
        headers=admin_headers,
    )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["slug"] == "ecole-demo"
    assert len(data["joinCode"]) == 10
    assert data["memberCount"] == 1
    manager = await db.scalar(select(User).where(User.email == "ri@ecole-demo.fr"))
    assert manager.account_type == AccountType.ORG_STAFF
    assert manager.password_hash is None
    member = await db.scalar(
        select(OrganizationMember).where(OrganizationMember.user_id == manager.id)
    )
    assert member.org_role == OrgRole.MANAGER
    assert await _audit_count(db) == 1


async def test_slugs_stay_unique(api, db, admin_headers):
    await make_organization(db, slug="ecole-demo")
    await db.commit()

    created = await api.post(
        "/admin/organizations",
        json={"name": "École Démo", "manager": {"email": "a@example.com", "name": "A"}},
        headers=admin_headers,
    )
    other = await make_organization(db)
    await db.commit()
    renamed = await api.patch(
        f"/admin/organizations/{other.id}", json={"slug": "ecole-demo"}, headers=admin_headers
    )

    assert created.json()["data"]["slug"] == "ecole-demo-2"
    assert renamed.status_code == 409


async def test_update_records_before_and_after(api, db, admin_headers):
    organization = await make_organization(db, name="Old")
    await db.commit()

    response = await api.patch(
        f"/admin/organizations/{organization.id}",
        json={"name": "New", "branding": {"primary_color": "#000000"}},
        headers=admin_headers,
    )

    assert response.status_code == 200
    entry = await db.scalar(select(AuditLog))
    assert entry.action == "organization.update"
    assert entry.changes["name"] == ["Old", "New"]


@pytest.fixture
async def team(db):
    organization = await make_organization(db)
    manager = await make_member(db, organization, OrgRole.MANAGER)
    advisor = await make_member(db, organization, OrgRole.ADVISOR)
    await db.commit()
    return organization, manager, advisor


@pytest.mark.parametrize(
    ("method", "body"),
    [("patch", {"orgRole": "advisor"}), ("patch", {"isActive": False}), ("delete", None)],
    ids=["demote", "deactivate", "remove"],
)
async def test_the_last_active_manager_is_protected(api, db, admin_headers, team, method, body):
    organization, manager, _ = team

    response = await api.request(
        method,
        f"/admin/organizations/{organization.id}/members/{manager.id}",
        json=body,
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "LAST_MANAGER"
    assert await _audit_count(db) == 0


async def test_promoting_a_second_manager_frees_the_first(api, db, admin_headers, team):
    organization, manager, advisor = team
    base = f"/admin/organizations/{organization.id}/members"

    promoted = await api.patch(
        f"{base}/{advisor.id}", json={"orgRole": "manager"}, headers=admin_headers
    )
    demoted = await api.patch(
        f"{base}/{manager.id}", json={"orgRole": "advisor"}, headers=admin_headers
    )

    assert promoted.status_code == demoted.status_code == 200
    assert demoted.json()["data"]["orgRole"] == "advisor"


async def test_a_role_change_revokes_the_member_sessions(api, db, admin_headers, team):
    organization, _, advisor = team
    staff = await db.get(User, advisor.user_id)
    headers = auth_headers(staff)

    await api.patch(
        f"/admin/organizations/{organization.id}/members/{advisor.id}",
        json={"orgRole": "manager"},
        headers=admin_headers,
    )

    assert (await api.get("/users/me", headers=headers)).status_code == 401


async def test_add_members(api, db, admin_headers, team):
    organization, _, _ = team
    student = await make_user(db, email="student@example.com")
    await db.commit()
    base = f"/admin/organizations/{organization.id}/members"

    added = await api.post(
        base,
        json={"email": "new@example.com", "name": "New", "orgRole": "advisor"},
        headers=admin_headers,
    )
    taken = await api.post(
        base,
        json={"email": student.email, "name": "S", "orgRole": "advisor"},
        headers=admin_headers,
    )
    listing = await api.get(base, headers=admin_headers)

    assert added.status_code == 201
    assert taken.status_code == 409
    assert len(listing.json()["data"]) == 3


async def test_enroll_and_revoke_a_student(api, db, admin_headers, team):
    organization, manager, _ = team
    student = await make_user(db)
    await db.commit()
    base = f"/admin/organizations/{organization.id}/students"

    enrolled = await api.post(base, json={"studentId": str(student.id)}, headers=admin_headers)
    staff = await api.post(base, json={"studentId": str(manager.user_id)}, headers=admin_headers)
    revoked = await api.delete(f"{base}/{student.id}", headers=admin_headers)
    history = await api.get(f"{base}?status=revoked", headers=admin_headers)

    assert enrolled.status_code == 201
    assert enrolled.json()["data"]["source"] == "admin"
    assert staff.json()["error"]["code"] == "NOT_A_STUDENT"
    assert revoked.status_code == 204
    assert [e["studentId"] for e in history.json()["data"]] == [str(student.id)]


async def test_a_student_already_enrolled_elsewhere_is_refused(api, db, admin_headers):
    first, second = await make_organization(db), await make_organization(db)
    student = await make_user(db)
    await make_enrollment(db, first, student)
    await db.commit()

    response = await api.post(
        f"/admin/organizations/{second.id}/students",
        json={"studentId": str(student.id)},
        headers=admin_headers,
    )

    assert response.json()["error"]["code"] == "ALREADY_ENROLLED"


async def test_suspending_an_organization_blocks_its_staff(api, db, admin_headers, team):
    organization, manager, _ = team

    response = await api.post(
        f"/admin/organizations/{organization.id}/suspend", headers=admin_headers
    )

    assert response.json()["data"]["status"] == "suspended"
    actor = await load_actor(db, await db.get(User, manager.user_id))
    await db.refresh(actor.organization)
    with pytest.raises(ForbiddenError):
        await require_org_role()(GET_REQUEST, actor, db)


async def test_archiving_revokes_enrollments_and_deactivates_staff(api, db, admin_headers, team):
    organization, _, _ = team
    student = await make_user(db)
    await make_enrollment(db, organization, student)
    await db.commit()

    archived = await api.post(
        f"/admin/organizations/{organization.id}/archive", headers=admin_headers
    )
    reactivated = await api.post(
        f"/admin/organizations/{organization.id}/reactivate", headers=admin_headers
    )

    data = archived.json()["data"]
    assert data["organization"]["status"] == "archived"
    assert len(data["deactivatedMembers"]) == 2
    enrollment = await db.scalar(select(StudentEnrollment))
    await db.refresh(enrollment)
    assert enrollment.status == EnrollmentStatus.REVOKED
    assert reactivated.json()["error"]["code"] == "LAST_MANAGER"
    entries = list(await db.scalars(select(AuditLog.action)))
    assert entries == ["organization.archive"]


async def test_list_and_search_organizations(api, db, admin_headers):
    await make_organization(db, name="Sciences Po Paris")
    await make_organization(db, name="INSA Lyon")
    await db.commit()

    response = await api.get("/admin/organizations?q=lyon", headers=admin_headers)

    assert [o["name"] for o in response.json()["data"]] == ["INSA Lyon"]
