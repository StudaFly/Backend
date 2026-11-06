"""Every `/org` route, called by every kind of actor."""

import re
import uuid

import pytest
from fastapi.routing import APIRoute
from src.app.main import app
from src.app.models.enums import OrganizationStatus

from tests.db.factories import auth_headers, make_platform_admin

PREFIX = "/api/v1"
ORG_ROUTES = sorted(
    (method, route.path.removeprefix(PREFIX))
    for route in app.routes
    if isinstance(route, APIRoute)
    and route.path.startswith(f"{PREFIX}/org/")
    or isinstance(route, APIRoute)
    and route.path == f"{PREFIX}/org"
    for method in route.methods
)
MANAGER_ONLY = {
    ("GET", "/org/contract"),
    ("PATCH", "/org"),
    ("POST", "/org/members"),
    ("PATCH", "/org/members/{member_id}"),
    ("DELETE", "/org/members/{member_id}"),
    ("PUT", "/org/members/{member_id}/perimeter"),
    ("DELETE", "/org/students/{student_id}"),
    ("PUT", "/org/mobilities/{mobility_id}/advisor"),
    ("DELETE", "/org/mobilities/{mobility_id}/advisor"),
    ("POST", "/org/join-code/rotate"),
    ("GET", "/org/audit-logs"),
}
OWN_RESOURCE_FOR_ADVISORS = {("GET", "/org/members/{member_id}/perimeter")}


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", lambda _: str(uuid.uuid4()), path)


@pytest.fixture
async def outsiders(db, school):
    admin = await make_platform_admin(db)
    await db.commit()
    return {
        "student": auth_headers(school.students["madrid"]),
        "platform_admin": auth_headers(admin, mfa=True),
    }


def test_the_org_surface_is_covered():
    assert len(ORG_ROUTES) >= 24
    assert MANAGER_ONLY <= set(ORG_ROUTES)


@pytest.mark.parametrize(("method", "path"), ORG_ROUTES)
async def test_org_route_permissions(api, db, school, outsiders, method, path):
    url = _concrete(path)
    body = {} if method in ("POST", "PATCH", "PUT") else None

    async def call(headers=None):
        return await api.request(method, url, json=body, headers=headers or {})

    assert (await call()).status_code == 401
    for name, headers in outsiders.items():
        assert (await call(headers)).status_code == 403, name
    advisor = (await call(school.headers("europe"))).status_code
    if (method, path) in MANAGER_ONLY | OWN_RESOURCE_FOR_ADVISORS:
        assert advisor == 403
    else:
        assert advisor not in (401, 403)
    assert (await call(school.headers("manager"))).status_code not in (401, 403)

    school.organization.status = OrganizationStatus.SUSPENDED
    await db.commit()
    assert (await call(school.headers("manager"))).status_code == 403
