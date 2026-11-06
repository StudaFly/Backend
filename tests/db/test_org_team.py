"""Organization settings, team management by managers and the organization audit log."""

from sqlalchemy import select
from src.app.models.audit_log import AuditLog

from tests.db.factories import auth_headers


async def test_managers_edit_branding_and_settings(api, db, school):
    payload = {"branding": {"primary_color": "#123456"}, "settings": {"email_digest": "weekly"}}

    advisor = await api.patch("/org", json=payload, headers=school.headers("europe"))
    name = await api.patch("/org", json={"name": "Renamed"}, headers=school.headers("manager"))
    manager = await api.patch("/org", json=payload, headers=school.headers("manager"))

    assert advisor.status_code == 403
    assert name.status_code == 422
    assert manager.json()["data"]["branding"] == {"primary_color": "#123456"}
    entry = await db.scalar(select(AuditLog).where(AuditLog.action == "organization.update"))
    assert entry.organization_id == school.organization.id


async def test_managers_run_their_team(api, school):
    manager = school.members["manager"]
    advisor = school.members["asia"]

    last_manager = await api.patch(
        f"/org/members/{manager.id}", json={"orgRole": "advisor"}, headers=school.headers("manager")
    )
    promoted = await api.patch(
        f"/org/members/{advisor.id}", json={"orgRole": "manager"}, headers=school.headers("manager")
    )
    by_advisor = await api.delete(f"/org/members/{advisor.id}", headers=school.headers("europe"))
    directory = await api.get("/org/members", headers=school.headers("europe"))

    assert last_manager.json()["error"]["code"] == "LAST_MANAGER"
    assert promoted.json()["data"]["orgRole"] == "manager"
    assert by_advisor.status_code == 403
    assert len(directory.json()["data"]) == 4


async def test_members_of_other_schools_are_out_of_reach(api, school):
    other_member = school.members["asia"].id

    response = await api.patch(
        f"/org/members/{other_member}",
        json={"isActive": False},
        headers=auth_headers(school.other_manager),
    )

    assert response.status_code == 404


async def test_managers_read_their_organization_log_only(api, school):
    await api.post("/org/join-code/rotate", headers=school.headers("manager"))
    await api.post("/org/join-code/rotate", headers=auth_headers(school.other_manager))

    advisor = await api.get("/org/audit-logs", headers=school.headers("europe"))
    manager = await api.get("/org/audit-logs", headers=school.headers("manager"))

    assert advisor.status_code == 403
    assert [e["organizationId"] for e in manager.json()["data"]] == [str(school.organization.id)]


async def test_zones_are_listed(api, school):
    response = await api.get("/org/zones", headers=school.headers("europe"))

    zones = {zone["key"]: zone["countries"] for zone in response.json()["data"]}
    assert set(zones) == {
        "europe",
        "africa",
        "north_america",
        "latin_america",
        "asia",
        "middle_east",
        "oceania",
    }
    assert "FR" in zones["europe"]
