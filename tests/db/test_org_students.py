"""Advisor perimeters, assignment resolution and what each staff member can see."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select
from src.app.models.audit_log import AuditLog
from src.app.models.document import Document

from tests.db.factories import auth_headers
from tests.db.school import add_tasks


async def _visible(api, school, who: str, query: str = "") -> set[str]:
    response = await api.get(f"/org/students{query}", headers=school.headers(who))
    assert response.status_code == 200, response.text
    return {item["email"].split("@")[0] for item in response.json()["data"]}


async def test_each_advisor_sees_the_students_of_their_perimeter(api, school):
    assert await _visible(api, school, "manager") == {
        "madrid",
        "new_york",
        "tokyo",
        "sydney",
        "lima",
    }
    assert await _visible(api, school, "europe") == {"madrid"}
    assert await _visible(api, school, "north_america") == {"new_york"}
    assert await _visible(api, school, "asia") == {"tokyo"}


async def test_unassigned_mobilities_are_flagged_for_managers(api, school):
    assert await _visible(api, school, "manager", "?unassigned=true") == {"sydney"}
    response = await api.get("/org/students?q=sydney", headers=school.headers("manager"))
    [item] = response.json()["data"]
    assert item["mobility"]["advisor"] is None
    assert item["mobility"]["assignment"] is None


async def test_filters_by_zone_and_advisor(api, school):
    asia = school.members["asia"].id

    assert await _visible(api, school, "manager", "?zone=europe") == {"madrid"}
    assert await _visible(api, school, "manager", f"?advisorId={asia}") == {"tokyo"}
    assert await _visible(api, school, "manager", "?zone=latin_america") == {"lima"}


@pytest.mark.parametrize(
    ("who", "student"),
    [("europe", "tokyo"), ("asia", "madrid"), ("north_america", "sydney")],
)
async def test_outside_the_perimeter_is_not_found(api, school, who, student):
    student_id = school.students[student].id

    for path in (f"/org/students/{student_id}", f"/org/students/{student_id}/notes"):
        assert (await api.get(path, headers=school.headers(who))).status_code == 404
    note = await api.post(
        f"/org/students/{student_id}/notes", json={"body": "x"}, headers=school.headers(who)
    )
    assert note.status_code == 404


async def test_another_schools_student_is_not_found(api, school):
    manager = auth_headers(school.other_manager)

    response = await api.get(f"/org/students/{school.students['madrid'].id}", headers=manager)
    listing = await api.get("/org/students", headers=manager)

    assert response.status_code == 404
    assert [s["email"] for s in listing.json()["data"]] == ["other-school@example.com"]


async def test_a_manual_assignment_wins_over_the_perimeter(api, school):
    mobility = school.mobilities["sydney"]
    europe = school.members["europe"]

    assigned = await api.put(
        f"/org/mobilities/{mobility.id}/advisor",
        json={"memberId": str(europe.id)},
        headers=school.headers("manager"),
    )

    assert assigned.status_code == 204
    assert await _visible(api, school, "europe") == {"madrid", "sydney"}
    response = await api.get("/org/students?q=sydney", headers=school.headers("europe"))
    assert response.json()["data"][0]["mobility"]["assignment"] == "override"

    cleared = await api.delete(
        f"/org/mobilities/{mobility.id}/advisor", headers=school.headers("manager")
    )
    assert cleared.status_code == 204
    assert await _visible(api, school, "europe") == {"madrid"}


async def test_an_override_to_a_deactivated_member_falls_back_to_the_perimeter(api, school):
    madrid = school.mobilities["madrid"]
    asia = school.members["asia"]
    await api.put(
        f"/org/mobilities/{madrid.id}/advisor",
        json={"memberId": str(asia.id)},
        headers=school.headers("manager"),
    )
    assert await _visible(api, school, "europe") == set()

    await api.patch(
        f"/org/members/{asia.id}", json={"isActive": False}, headers=school.headers("manager")
    )

    assert await _visible(api, school, "europe") == {"madrid"}


async def test_a_perimeter_change_applies_immediately(api, school):
    north_america = school.members["north_america"]

    response = await api.put(
        f"/org/members/{north_america.id}/perimeter",
        json={"countries": ["US", "CA", "AU"]},
        headers=school.headers("manager"),
    )

    assert response.status_code == 200
    assert response.json()["data"]["countries"] == ["AU", "CA", "US"]
    assert await _visible(api, school, "north_america") == {"new_york", "sydney"}


async def test_a_country_belongs_to_a_single_perimeter(api, db, school):
    asia = school.members["asia"]
    path = f"/org/members/{asia.id}/perimeter"
    countries = ["ES", "JP"]

    refused = await api.put(path, json={"countries": countries}, headers=school.headers("manager"))
    moved = await api.put(
        path, json={"countries": countries, "reassign": True}, headers=school.headers("manager")
    )

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "COUNTRY_ALREADY_ASSIGNED"
    assert moved.status_code == 200
    assert await _visible(api, school, "asia") == {"madrid", "tokyo"}
    assert await _visible(api, school, "europe") == set()
    entry = await db.scalar(select(AuditLog).where(AuditLog.action == "perimeter.update"))
    assert entry.changes["added"] == ["ES"]
    assert entry.changes["reassigned_from"] == {"ES": str(school.members["europe"].id)}


async def test_perimeter_validation(api, school):
    member = school.members["asia"]

    response = await api.put(
        f"/org/members/{member.id}/perimeter",
        json={"countries": ["ZZ"]},
        headers=school.headers("manager"),
    )

    assert response.status_code == 422


async def test_an_advisor_only_reads_their_own_perimeter(api, school):
    own = await api.get(
        f"/org/members/{school.members['europe'].id}/perimeter", headers=school.headers("europe")
    )
    other = await api.get(
        f"/org/members/{school.members['asia'].id}/perimeter", headers=school.headers("europe")
    )
    org = await api.get("/org", headers=school.headers("europe"))

    assert own.json()["data"]["zones"] == ["europe", "africa"]
    assert other.status_code == 403
    assert org.json()["data"]["myZones"] == ["europe", "africa"]
    assert org.json()["data"]["myOrgRole"] == "advisor"


async def test_completed_mobilities_leave_the_advisor_scope(api, db, school):
    school.mobilities["madrid"].status = "completed"
    await db.commit()

    assert await _visible(api, school, "europe") == set()


async def test_student_record_shows_progress_and_document_status_only(api, db, school):
    mobility = school.mobilities["madrid"]
    await add_tasks(db, mobility, done=1, todo=1)
    db.add(
        Document(mobility_id=mobility.id, file_url="s3://private/passport.pdf", category="identity")
    )
    await db.commit()

    response = await api.get(
        f"/org/students/{school.students['madrid'].id}", headers=school.headers("europe")
    )

    assert response.status_code == 200
    [detail] = response.json()["data"]["mobilities"]
    assert detail["progress"] == 50
    assert {c["category"]: (c["done"], c["total"]) for c in detail["categories"]} == {
        "admin": (1, 1),
        "finance": (0, 1),
    }
    assert detail["documents"][0]["category"] == "identity"
    assert "s3://" not in response.text


async def test_follow_up_status(api, db, school):
    madrid, tokyo = school.mobilities["madrid"], school.mobilities["tokyo"]
    madrid.departure_date = date.today() + timedelta(days=10)
    await db.commit()
    await add_tasks(db, madrid, done=0, todo=4)
    await add_tasks(db, tokyo, done=3, todo=0, overdue=1)

    states = {
        item["email"].split("@")[0]: item["followUp"]
        for item in (await api.get("/org/students", headers=school.headers("manager"))).json()[
            "data"
        ]
    }

    assert states["madrid"] == "danger"
    assert states["tokyo"] == "warning"
    assert states["lima"] == "ok"
    assert await _visible(api, school, "manager", "?status=danger") == {"madrid"}


async def test_notes_are_shared_by_the_staff_who_can_see_the_student(api, school):
    student = school.students["madrid"].id
    path = f"/org/students/{student}/notes"

    created = await api.post(
        path, json={"body": "Visa appointment booked"}, headers=school.headers("europe")
    )
    seen_by_manager = await api.get(path, headers=school.headers("manager"))

    assert created.status_code == 201
    [note] = seen_by_manager.json()["data"]
    assert note["body"] == "Visa appointment booked"
    assert note["author"]["memberId"] == str(school.members["europe"].id)
    me = await api.get("/users/me", headers=auth_headers(school.students["madrid"]))
    assert "Visa appointment" not in me.text
