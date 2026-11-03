"""Cross-student isolation (404, not 403), data invariants enforced by the database and the
account-type / organization-role guards."""

import pytest
from sqlalchemy.exc import IntegrityError
from src.app.authz import load_actor, require_account_type, require_org_role
from src.app.core.exceptions import ForbiddenError
from src.app.models.enums import AccountType, EnrollmentStatus, OrganizationStatus, OrgRole
from src.app.models.task import Task
from src.app.models.user import User

from tests.db.factories import (
    auth_headers,
    make_destination,
    make_enrollment,
    make_member,
    make_mobility,
    make_organization,
    make_user,
)


@pytest.fixture
async def other_students_mobility(db):
    owner = await make_user(db)
    intruder = await make_user(db)
    mobility = await make_mobility(db, owner, await make_destination(db))
    task = Task(mobility_id=mobility.id, title="Visa", category="admin", priority=1)
    db.add(task)
    await db.commit()
    return intruder, mobility, task


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/mobilities/{mobility}"),
        ("patch", "/mobilities/{mobility}"),
        ("delete", "/mobilities/{mobility}"),
        ("get", "/mobilities/{mobility}/timeline"),
        ("get", "/mobilities/{mobility}/progress"),
        ("get", "/mobilities/{mobility}/tasks"),
        ("post", "/mobilities/{mobility}/tasks"),
        ("patch", "/tasks/{task}"),
        ("patch", "/tasks/{task}/complete"),
        ("delete", "/tasks/{task}"),
    ],
)
async def test_another_students_mobility_is_not_found(
    api, db, other_students_mobility, method, path
):
    intruder, mobility, task = other_students_mobility
    body = {"title": "Mine now", "category": "admin"} if method in ("post", "patch") else None

    response = await api.request(
        method,
        path.format(mobility=mobility.id, task=task.id),
        json=body,
        headers=auth_headers(intruder),
    )

    assert response.status_code == 404
    await db.refresh(task)
    assert (task.title, task.is_completed) == ("Visa", False)



async def test_a_student_has_a_single_active_enrollment(db):
    first, second = await make_organization(db), await make_organization(db)
    student = await make_user(db)
    await make_enrollment(db, first, student)

    with pytest.raises(IntegrityError):
        await make_enrollment(db, second, student)


async def test_enrollment_history_is_kept(db):
    first, second = await make_organization(db), await make_organization(db)
    student = await make_user(db)
    await make_enrollment(db, first, student, status=EnrollmentStatus.LEFT)
    await make_enrollment(db, first, student, status=EnrollmentStatus.REVOKED)

    await make_enrollment(db, second, student)


async def test_a_staff_member_belongs_to_a_single_organization(db):
    first, second = await make_organization(db), await make_organization(db)
    member = await make_member(db, first)
    staff = await db.get(User, member.user_id)

    with pytest.raises(IntegrityError):
        await make_member(db, second, user=staff)


async def test_join_codes_are_unique(db):
    organization = await make_organization(db)

    with pytest.raises(IntegrityError):
        await make_organization(db, join_code=organization.join_code)



async def test_creating_a_destination_is_reserved_to_platform_admins(api, db):
    student = await make_user(db)
    admin = await make_user(db, AccountType.PLATFORM_ADMIN)
    await db.commit()
    payload = {"country": "Brésil", "countryCode": "BR", "city": "São Paulo"}

    refused = await api.post("/destinations", json=payload, headers=auth_headers(student))
    created = await api.post("/destinations", json=payload, headers=auth_headers(admin))

    assert refused.status_code == 403
    assert created.status_code == 201
    assert created.json()["data"]["countryCode"] == "BR"


async def test_require_account_type(db):
    student = await make_user(db)
    guard = require_account_type(AccountType.ORG_STAFF, AccountType.PLATFORM_ADMIN)

    with pytest.raises(ForbiddenError):
        await guard(await load_actor(db, student))


async def _staff_actor(db, org_role=OrgRole.ADVISOR, is_active=True, org_status=None):
    organization = await make_organization(db, status=org_status or OrganizationStatus.ACTIVE)
    member = await make_member(db, organization, org_role, is_active=is_active)
    return await load_actor(db, await db.get(User, member.user_id))


async def test_require_org_role_accepts_an_active_member(db):
    actor = await _staff_actor(db, OrgRole.MANAGER)

    assert await require_org_role(OrgRole.MANAGER)(actor) is actor
    assert await require_org_role()(actor) is actor


@pytest.mark.parametrize(
    ("org_role", "is_active", "org_status"),
    [
        (OrgRole.ADVISOR, True, OrganizationStatus.ACTIVE),
        (OrgRole.MANAGER, False, OrganizationStatus.ACTIVE),
        (OrgRole.MANAGER, True, OrganizationStatus.SUSPENDED),
        (OrgRole.MANAGER, True, OrganizationStatus.ARCHIVED),
    ],
    ids=["advisor-on-manager-route", "deactivated-member", "suspended-org", "archived-org"],
)
async def test_require_org_role_refuses(db, org_role, is_active, org_status):
    actor = await _staff_actor(db, org_role, is_active, org_status)

    with pytest.raises(ForbiddenError):
        await require_org_role(OrgRole.MANAGER)(actor)
