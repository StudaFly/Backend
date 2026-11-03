"""`GET /users/me`: account type and organization, plus the deprecated fields kept for the
current clients until the contract migration."""

from src.app.models.enums import AccountType, EnrollmentStatus, OrganizationStatus, OrgRole
from src.app.models.user import User

from tests.db.factories import (
    auth_headers,
    make_enrollment,
    make_member,
    make_organization,
    make_user,
)


async def _me(api, user: User) -> dict:
    response = await api.get("/users/me", headers=auth_headers(user))
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def test_independent_student(api, db):
    student = await make_user(db)
    await db.commit()

    me = await _me(api, student)

    assert me["accountType"] == "student"
    assert me["orgRole"] is None
    assert me["organization"] is None
    assert (me["role"], me["institutionId"]) == ("student", None)


async def test_enrolled_student_sees_their_organization(api, db):
    organization = await make_organization(
        db, name="École Démo", branding={"primary_color": "#213458"}
    )
    student = await make_user(db)
    await make_enrollment(db, organization, student)
    await db.commit()

    me = await _me(api, student)

    assert me["organization"] == {
        "id": str(organization.id),
        "name": "École Démo",
        "slug": organization.slug,
        "logoUrl": None,
        "branding": {"primary_color": "#213458"},
    }
    assert me["institutionId"] == str(organization.id)


async def test_past_enrollment_is_not_the_current_organization(api, db):
    organization = await make_organization(db)
    student = await make_user(db)
    await make_enrollment(db, organization, student, status=EnrollmentStatus.LEFT)
    await db.commit()

    me = await _me(api, student)

    assert me["organization"] is None


async def test_staff_member_gets_org_role(api, db):
    organization = await make_organization(db)
    member = await make_member(db, organization, OrgRole.ADVISOR)
    staff = await db.get(User, member.user_id)
    await db.commit()

    me = await _me(api, staff)

    assert me["accountType"] == "org_staff"
    assert me["orgRole"] == "advisor"
    assert me["organization"]["id"] == str(organization.id)
    assert me["role"] == "admin"  # deprecated mapping read by the current mobile app


async def test_deactivated_member_has_no_organization(api, db):
    organization = await make_organization(db, status=OrganizationStatus.ACTIVE)
    member = await make_member(db, organization, OrgRole.MANAGER, is_active=False)
    staff = await db.get(User, member.user_id)
    await db.commit()

    me = await _me(api, staff)

    assert (me["orgRole"], me["organization"]) == (None, None)


async def test_platform_admin(api, db):
    admin = await make_user(db, AccountType.PLATFORM_ADMIN)
    await db.commit()

    me = await _me(api, admin)

    assert me["accountType"] == "platform_admin"
    assert me["organization"] is None
    assert me["role"] == "superadmin"


async def test_profile_update_returns_the_same_shape(api, db):
    student = await make_user(db)
    await db.commit()

    response = await api.patch(
        "/users/me", json={"phone": "0600000000"}, headers=auth_headers(student)
    )

    assert response.status_code == 200
    assert response.json()["data"]["accountType"] == "student"
    assert response.json()["data"]["phone"] == "0600000000"
