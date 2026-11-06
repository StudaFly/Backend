"""Student and staff invitations, CSV import, school code, leaving a school."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from src.app.models.enums import AccountType, EnrollmentSource, OrganizationStatus
from src.app.models.invitation import Invitation
from src.app.models.student_enrollment import StudentEnrollment
from src.app.services import invitation_service

from tests.db.factories import PASSWORD, auth_headers, make_enrollment, make_organization, make_user


@pytest.fixture
def links(monkeypatch) -> dict[str, str]:
    sent: dict[str, str] = {}
    monkeypatch.setattr(
        invitation_service, "_log_link", lambda email, token: sent.__setitem__(email, token)
    )
    return sent


async def _invite(api, school, email: str, who: str = "europe"):
    response = await api.post(
        "/org/invitations", json={"email": email}, headers=school.headers(who)
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def test_a_student_accepts_an_invitation_after_signing_up(api, db, school, links):
    await _invite(api, school, "Lucas@Example.com")
    token = links["lucas@example.com"]

    preview = await api.get(f"/invitations/{token}")
    anonymous = await api.post(f"/invitations/{token}/accept")
    register = await api.post(
        "/auth/register", json={"email": "lucas@example.com", "password": PASSWORD, "name": "Lucas"}
    )
    headers = {"Authorization": f"Bearer {register.json()['data']['accessToken']}"}
    accepted = await api.post(f"/invitations/{token}/accept", headers=headers)
    again = await api.post(f"/invitations/{token}/accept", headers=headers)
    me = await api.get("/users/me", headers=headers)

    data = preview.json()["data"]
    assert data["organization"]["name"] == "École Démo"
    assert "document_content" in data["neverShared"]
    assert anonymous.status_code == 401
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["data"]["auth"] is None
    assert again.json()["error"]["code"] == "INVITATION_NOT_PENDING"
    assert me.json()["data"]["organization"]["id"] == str(school.organization.id)
    enrollment = await db.scalar(
        select(StudentEnrollment).order_by(StudentEnrollment.created_at.desc())
    )
    assert enrollment.source == EnrollmentSource.INVITATION


async def test_an_invitation_is_bound_to_its_email(api, db, school, links):
    intruder = await make_user(db)
    await db.commit()
    await _invite(api, school, "lucas@example.com")

    response = await api.post(
        f"/invitations/{links['lucas@example.com']}/accept", headers=auth_headers(intruder)
    )

    assert response.status_code == 403


async def test_a_student_of_another_school_must_leave_first(api, school, links):
    await _invite(api, school, school.other_student.email)

    response = await api.post(
        f"/invitations/{links[school.other_student.email]}/accept",
        headers=auth_headers(school.other_student),
    )

    assert response.json()["error"]["code"] == "ALREADY_ENROLLED"


async def test_expired_invitations(api, db, school, links):
    invitation = await _invite(api, school, "late@example.com")
    row = await db.get(Invitation, invitation["id"])
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db.commit()
    student = await make_user(db, email="late@example.com")
    await db.commit()

    preview = await api.get(f"/invitations/{links['late@example.com']}")
    accept = await api.post(
        f"/invitations/{links['late@example.com']}/accept", headers=auth_headers(student)
    )

    assert preview.json()["data"]["status"] == "expired"
    assert accept.status_code == 409


async def test_resending_replaces_the_link(api, school, links):
    first = await _invite(api, school, "lucas@example.com")
    old_token = links["lucas@example.com"]
    second = await _invite(api, school, "lucas@example.com", who="manager")

    assert first["id"] == second["id"]
    assert (await api.get(f"/invitations/{old_token}")).status_code == 404
    assert (await api.get(f"/invitations/{links['lucas@example.com']}")).status_code == 200


async def test_inviting_staff_or_enrolled_students_is_refused(api, school):
    staff = await api.post(
        "/org/invitations",
        json={"email": school.staff["asia"].email},
        headers=school.headers("europe"),
    )
    member = await api.post(
        "/org/invitations",
        json={"email": school.students["madrid"].email},
        headers=school.headers("europe"),
    )

    assert staff.json()["error"]["code"] == "NOT_A_STUDENT"
    assert member.json()["error"]["code"] == "ALREADY_MEMBER"


async def test_csv_import_reports_each_line(api, db, school, links):
    content = (
        "Email;Nom\n"
        "alice@example.com;Alice\n"
        "not-an-email;X\n"
        "ALICE@example.com;Alice again\n"
        f"{school.students['madrid'].email};Already\n"
        f"{school.staff['asia'].email};Staff\n"
        "bob@example.com;Bob\n"
    )

    response = await api.post(
        "/org/invitations/import",
        files={"file": ("students.csv", content.encode(), "text/csv")},
        headers=school.headers("europe"),
    )

    assert response.status_code == 200, response.text
    report = response.json()["data"]
    assert (report["invited"], report["resent"], report["skipped"]) == (2, 0, 4)
    assert [(line["line"], line["status"]) for line in report["lines"]] == [
        (2, "invited"),
        (3, "invalid_email"),
        (4, "duplicate"),
        (5, "already_member"),
        (6, "not_a_student"),
        (7, "invited"),
    ]
    student = await make_user(db, email="bob@example.com")
    await db.commit()
    await api.post(f"/invitations/{links['bob@example.com']}/accept", headers=auth_headers(student))
    enrollment = await db.scalar(
        select(StudentEnrollment).where(StudentEnrollment.student_id == student.id)
    )
    assert enrollment.source == EnrollmentSource.CSV_IMPORT


async def test_csv_without_email_column_is_rejected(api, school):
    response = await api.post(
        "/org/invitations/import",
        files={"file": ("students.csv", b"name\nAlice\n", "text/csv")},
        headers=school.headers("manager"),
    )

    assert response.status_code == 422


async def test_staff_invitation_creates_the_account(api, db, school, links):
    response = await api.post(
        "/org/members",
        json={"email": "new-advisor@example.com", "orgRole": "advisor"},
        headers=school.headers("manager"),
    )
    token = links["new-advisor@example.com"]

    missing_password = await api.post(f"/invitations/{token}/accept", json={"name": "New"})
    accepted = await api.post(
        f"/invitations/{token}/accept", json={"name": "New Advisor", "password": "advisor-pass-1"}
    )

    assert response.status_code == 201
    assert missing_password.status_code == 422
    assert accepted.status_code == 200, accepted.text
    auth = accepted.json()["data"]["auth"]
    assert auth["user"]["accountType"] == "org_staff"
    assert auth["user"]["orgRole"] == "advisor"
    org = await api.get("/org", headers={"Authorization": f"Bearer {auth['accessToken']}"})
    assert org.status_code == 200


async def test_staff_invitations_are_managed_by_managers(api, school):
    advisor_invite = await api.post(
        "/org/members",
        json={"email": "x@example.com", "orgRole": "manager"},
        headers=school.headers("europe"),
    )
    student_email = await api.post(
        "/org/members",
        json={"email": school.students["madrid"].email, "orgRole": "advisor"},
        headers=school.headers("manager"),
    )
    await api.post(
        "/org/members",
        json={"email": "staff@example.com", "orgRole": "advisor"},
        headers=school.headers("manager"),
    )
    advisor_list = await api.get("/org/invitations", headers=school.headers("europe"))
    manager_list = await api.get("/org/invitations?kind=staff", headers=school.headers("manager"))

    assert advisor_invite.status_code == 403
    assert student_email.json()["error"]["code"] == "ACCOUNT_EXISTS"
    assert advisor_list.json()["data"] == []
    assert [i["email"] for i in manager_list.json()["data"]] == ["staff@example.com"]


async def test_revoking_an_invitation(api, school, links):
    invitation = await _invite(api, school, "lucas@example.com")

    revoked = await api.delete(
        f"/org/invitations/{invitation['id']}", headers=school.headers("europe")
    )
    again = await api.delete(
        f"/org/invitations/{invitation['id']}", headers=school.headers("europe")
    )
    elsewhere = await api.delete(
        f"/org/invitations/{invitation['id']}", headers=auth_headers(school.other_manager)
    )

    assert revoked.status_code == 204
    assert again.status_code == 409
    assert elsewhere.status_code == 404
    assert (await api.get(f"/invitations/{links['lucas@example.com']}")).json()["data"][
        "status"
    ] == "revoked"


async def test_join_with_the_school_code_then_leave(api, db, school):
    student = await make_user(db)
    await db.commit()
    headers = auth_headers(student)
    code = (await api.get("/org/join-code", headers=school.headers("europe"))).json()["data"][
        "joinCode"
    ]
    typed = f"{code[:5].lower()}-{code[5:]}"

    preview = await api.get(f"/organizations/by-code/{typed}", headers=headers)
    joined = await api.post("/organizations/join", json={"code": typed}, headers=headers)
    twice = await api.post("/organizations/join", json={"code": code}, headers=headers)
    left = await api.delete("/users/me/organization", headers=headers)
    left_again = await api.delete("/users/me/organization", headers=headers)
    me = await api.get("/users/me", headers=headers)

    assert preview.json()["data"]["organization"]["name"] == "École Démo"
    assert joined.status_code == 200
    assert twice.json()["error"]["code"] == "ALREADY_ENROLLED"
    assert left.status_code == 204
    assert left_again.status_code == 404
    assert me.json()["data"]["organization"] is None


async def test_rotating_the_code_invalidates_the_old_one(api, db, school):
    student = await make_user(db)
    await db.commit()
    old = school.organization.join_code

    advisor = await api.post("/org/join-code/rotate", headers=school.headers("europe"))
    rotated = await api.post("/org/join-code/rotate", headers=school.headers("manager"))

    assert advisor.status_code == 403
    assert rotated.json()["data"]["joinCode"] != old
    response = await api.post(
        "/organizations/join", json={"code": old}, headers=auth_headers(student)
    )
    assert response.status_code == 404


async def test_only_students_use_school_codes(api, school):
    code = school.organization.join_code

    for headers in (school.headers("europe"), auth_headers(school.other_manager)):
        response = await api.post("/organizations/join", json={"code": code}, headers=headers)
        assert response.status_code == 403


async def test_a_suspended_school_cannot_be_joined(api, db, school):
    student = await make_user(db, account_type=AccountType.STUDENT)
    school.organization.status = OrganizationStatus.SUSPENDED
    await db.commit()

    response = await api.post(
        "/organizations/join",
        json={"code": school.organization.join_code},
        headers=auth_headers(student),
    )

    assert response.status_code == 404


async def test_managers_revoke_students(api, db, school):
    student = school.students["madrid"]

    advisor = await api.delete(f"/org/students/{student.id}", headers=school.headers("europe"))
    manager = await api.delete(f"/org/students/{student.id}", headers=school.headers("manager"))
    other = await make_organization(db)
    await make_enrollment(db, other, await make_user(db))
    await db.commit()

    assert advisor.status_code == 403
    assert manager.status_code == 204
    assert await _visible_count(api, school) == 4


async def _visible_count(api, school) -> int:
    return (await api.get("/org/students", headers=school.headers("manager"))).json()["total"]
