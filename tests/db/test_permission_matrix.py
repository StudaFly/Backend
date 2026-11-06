"""Every `/admin` route, called by every kind of actor (§13 of the roles spec)."""

import re
import uuid

import pytest
from fastapi.routing import APIRoute
from src.app.main import app
from src.app.models.enums import AccountType, OrgRole
from src.app.models.user import User

from tests.db.factories import (
    auth_headers,
    make_member,
    make_organization,
    make_platform_admin,
    make_user,
)

PREFIX = "/api/v1"
ADMIN_ROUTES = sorted(
    (method, route.path.removeprefix(PREFIX))
    for route in app.routes
    if isinstance(route, APIRoute) and route.path.startswith(f"{PREFIX}/admin")
    for method in route.methods
)


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", lambda _: str(uuid.uuid4()), path)


@pytest.fixture
async def actors(db):
    organization = await make_organization(db)
    manager = await make_member(db, organization, OrgRole.MANAGER)
    advisor = await make_member(db, organization, OrgRole.ADVISOR)
    other_manager = await make_member(db, await make_organization(db), OrgRole.MANAGER)
    admin = await make_platform_admin(db)
    actors = {
        "student": auth_headers(await make_user(db)),
        "advisor": auth_headers(await db.get(User, advisor.user_id)),
        "manager": auth_headers(await db.get(User, manager.user_id)),
        "manager_other_org": auth_headers(await db.get(User, other_manager.user_id)),
        "platform_admin_without_mfa": auth_headers(admin),
        "platform_admin_mfa_not_enabled": auth_headers(
            await make_user(db, AccountType.PLATFORM_ADMIN), mfa=True
        ),
        "platform_admin": auth_headers(admin, mfa=True),
    }
    await db.commit()
    return actors


def test_the_admin_surface_is_covered():
    assert len(ADMIN_ROUTES) >= 20


@pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
async def test_admin_route_permissions(api, actors, method, path):
    url = _concrete(path)
    body = {} if method in ("POST", "PATCH", "PUT") else None

    async def call(headers=None):
        return await api.request(method, url, json=body, headers=headers or {})

    assert (await call()).status_code == 401
    for name in ("student", "advisor", "manager", "manager_other_org"):
        assert (await call(actors[name])).status_code == 403, name
    for name in ("platform_admin_without_mfa", "platform_admin_mfa_not_enabled"):
        response = await call(actors[name])
        assert response.status_code == 403, name
        assert response.json()["error"]["code"] == "MFA_REQUIRED"
    assert (await call(actors["platform_admin"])).status_code not in (401, 403)
