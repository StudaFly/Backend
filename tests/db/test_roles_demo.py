"""The `seeds.roles_demo` dataset reproduces the case described in §12 of the roles spec."""

import pytest
from seeds import roles_demo
from seeds.seed import seed_destination_profiles, seed_destinations
from sqlalchemy import func, select
from src.app.authz import load_actor
from src.app.authz.scopes import visible_student_ids
from src.app.core.config import settings
from src.app.models.contract import Contract
from src.app.models.enums import AccountType, InvitationStatus, UserStatus
from src.app.models.invitation import Invitation
from src.app.models.user import User
from src.app.services import entitlements, org_student_service


async def _user(db, local: str) -> User:
    return await db.scalar(select(User).where(User.email == roles_demo.email(local)))


@pytest.fixture
async def demo(db):
    await seed_destinations(db)
    await db.flush()
    await seed_destination_profiles(db)
    await db.commit()
    await roles_demo.build(db)
    return db


async def test_accounts_and_contracts(demo):
    db = demo
    by_type = dict(
        (
            await db.execute(select(User.account_type, func.count()).group_by(User.account_type))
        ).all()
    )
    statuses = sorted(s.value for s in await db.scalars(select(Contract.status)))

    assert by_type[AccountType.PLATFORM_ADMIN] == 1
    assert by_type[AccountType.ORG_STAFF] == 6
    assert statuses == ["active", "expired", "pilot"]
    assert (await _user(db, "suspendu")).status == UserStatus.SUSPENDED
    pending = await db.scalar(
        select(func.count())
        .select_from(Invitation)
        .where(Invitation.status == InvitationStatus.PENDING)
    )
    assert pending == 2


async def test_each_advisor_sees_their_zone(demo):
    db = demo
    visible = {}
    for local in ("manager", "conseiller.europe", "conseiller.amerique", "conseiller.asie"):
        actor = await load_actor(db, await _user(db, local))
        visible[local] = len(list(await db.scalars(visible_student_ids(actor))))

    assert visible == {
        "manager": 13,
        "conseiller.europe": 5,
        "conseiller.amerique": 2,
        "conseiller.asie": 3,
    }
    manager = await load_actor(db, await _user(db, "manager"))
    unassigned, _ = await org_student_service.list_students(
        db, manager, page=1, per_page=50, unassigned=True
    )
    assert [s.name for s in unassigned] == ["Zoé Blanc"]
    states = {
        s.name: s.follow_up
        for s in (await org_student_service.list_students(db, manager, page=1, per_page=50))[0]
    }
    assert states["Emma Durand"] == "danger"
    assert states["Tom Lefebvre"] == "warning"


async def test_premium_sources(demo):
    db = demo
    expected = {
        "emma.durand": "organization",
        "pilote.alice": "organization",
        "expiree.encours": "grandfathered",
        "expiree.terminee": None,
        "libre": None,
        "premium": "purchase",
    }

    for local, source in expected.items():
        premium = await entitlements.premium_for(db, (await _user(db, local)).id)
        assert premium.source == source, local


async def test_the_demo_refuses_production(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")

    with pytest.raises(SystemExit, match="production"):
        await roles_demo.run(reset_first=False)
