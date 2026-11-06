"""B2B contracts: one current contract, quota, expiry and the effect on the school staff."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select
from src.app.models.audit_log import AuditLog
from src.app.models.contract import Contract
from src.app.models.enums import ContractStatus
from src.app.services import contract_service

from tests.db.factories import (
    auth_headers,
    make_contract,
    make_enrollment,
    make_organization,
    make_platform_admin,
    make_user,
)


@pytest.fixture
async def admin_headers(db):
    admin = await make_platform_admin(db)
    await db.commit()
    return auth_headers(admin, mfa=True)


def _payload(**overrides) -> dict:
    today = date.today()
    return {
        "plan": "standard",
        "status": "active",
        "startDate": today.isoformat(),
        "endDate": (today + timedelta(days=365)).isoformat(),
        "priceCents": 150_000,
        "studentQuota": 50,
        "notes": "Signed by the dean",
        **overrides,
    }


async def test_create_update_and_list_contracts(api, db, admin_headers):
    organization = await make_organization(db)
    await db.commit()
    base = f"/admin/organizations/{organization.id}/contracts"

    created = await api.post(base, json=_payload(), headers=admin_headers)
    contract_id = created.json()["data"]["id"]
    updated = await api.patch(
        f"{base}/{contract_id}", json={"studentQuota": 80}, headers=admin_headers
    )
    listing = await api.get(base, headers=admin_headers)
    expiring = await api.get("/admin/contracts?expiringWithin=400", headers=admin_headers)
    not_expiring = await api.get("/admin/contracts?expiringWithin=30", headers=admin_headers)

    assert created.status_code == 201, created.text
    assert updated.json()["data"]["studentQuota"] == 80
    assert len(listing.json()["data"]) == 1
    assert expiring.json()["total"] == 1
    assert not_expiring.json()["total"] == 0
    actions = list(await db.scalars(select(AuditLog.action).order_by(AuditLog.created_at)))
    assert actions == ["contract.create", "contract.update"]
    assert "dean" not in str(list(await db.scalars(select(AuditLog.changes))))


@pytest.mark.parametrize(
    ("overrides", "status_code"),
    [
        ({"status": "pilot", "priceCents": 1000}, 422),
        ({"endDate": (date.today() - timedelta(days=1)).isoformat()}, 422),
        ({"currency": "euro"}, 422),
    ],
    ids=["paid-pilot", "end-before-start", "currency"],
)
async def test_contract_validation(api, db, admin_headers, overrides, status_code):
    organization = await make_organization(db)
    await db.commit()

    response = await api.post(
        f"/admin/organizations/{organization.id}/contracts",
        json=_payload(**overrides),
        headers=admin_headers,
    )

    assert response.status_code == status_code


async def test_a_single_current_contract_per_organization(api, db, admin_headers):
    organization = await make_organization(db)
    await make_contract(db, organization)
    await db.commit()
    base = f"/admin/organizations/{organization.id}/contracts"

    overlap = await api.post(base, json=_payload(), headers=admin_headers)
    after = await api.post(
        base,
        json=_payload(
            startDate=(date.today() + timedelta(days=400)).isoformat(),
            endDate=(date.today() + timedelta(days=700)).isoformat(),
        ),
        headers=admin_headers,
    )

    assert overlap.json()["error"]["code"] == "CONTRACT_OVERLAP"
    assert after.status_code == 201


async def test_the_quota_limits_new_enrollments(api, db, school):
    await make_contract(db, school.organization, student_quota=5)
    await db.commit()
    newcomer = await make_user(db)
    await db.commit()

    joined = await api.post(
        "/organizations/join",
        json={"code": school.organization.join_code},
        headers=auth_headers(newcomer),
    )
    invited = await api.post(
        "/org/invitations", json={"email": "pending@example.com"}, headers=school.headers("manager")
    )

    assert joined.json()["error"]["code"] == "QUOTA_EXCEEDED"
    assert invited.status_code == 201


async def test_an_expired_contract_makes_the_staff_read_only(api, db, school):
    await make_contract(
        db,
        school.organization,
        ContractStatus.EXPIRED,
        date.today() - timedelta(days=400),
        date.today() - timedelta(days=1),
    )
    await db.commit()
    newcomer = await make_user(db)
    await db.commit()

    read = await api.get("/org/students", headers=school.headers("europe"))
    write = await api.post(
        "/org/invitations", json={"email": "x@example.com"}, headers=school.headers("europe")
    )
    joined = await api.post(
        "/organizations/join",
        json={"code": school.organization.join_code},
        headers=auth_headers(newcomer),
    )
    view = await api.get("/org/contract", headers=school.headers("manager"))

    assert read.status_code == 200
    assert write.json()["error"]["code"] == "CONTRACT_EXPIRED"
    assert joined.json()["error"]["code"] == "CONTRACT_INACTIVE"
    assert view.json()["data"]["state"] == "read_only"


@pytest.mark.parametrize("status", [ContractStatus.SUSPENDED, ContractStatus.CANCELLED])
async def test_a_suspended_or_cancelled_contract_blocks_the_staff(api, db, school, status):
    await make_contract(db, school.organization, status)
    await db.commit()

    response = await api.get("/org/students", headers=school.headers("manager"))

    assert response.json()["error"]["code"] == "CONTRACT_INACTIVE"


async def test_the_manager_sees_the_contract_terms_without_internal_notes(api, db, school):
    await make_contract(db, school.organization, student_quota=50, notes="Discount agreed")
    await db.commit()

    response = await api.get("/org/contract", headers=school.headers("manager"))

    data = response.json()["data"]
    assert data["state"] == "current"
    assert data["contract"]["studentQuota"] == 50
    assert data["activeStudents"] == 5
    assert "Discount" not in response.text


async def test_the_daily_job_expires_ended_contracts(db):
    organization = await make_organization(db)
    ended = await make_contract(
        db,
        organization,
        start=date.today() - timedelta(days=365),
        end=date.today() - timedelta(days=1),
    )
    current = await make_contract(
        db, await make_organization(db), start=date.today(), end=date.today() + timedelta(days=10)
    )
    await db.commit()

    assert await contract_service.expire_contracts(db) == 1
    assert await contract_service.expire_contracts(db) == 0

    await db.refresh(ended)
    await db.refresh(current)
    assert (ended.status, current.status) == (ContractStatus.EXPIRED, ContractStatus.ACTIVE)
    entry = await db.scalar(select(AuditLog).where(AuditLog.action == "contract.expire"))
    assert entry.actor_account_type == "cli"


async def test_overview_counts_contracts_and_premium(api, db, admin_headers):
    organization = await make_organization(db)
    await make_contract(db, organization, ContractStatus.PILOT)
    await make_enrollment(db, organization, await make_user(db))
    await db.commit()

    data = (await api.get("/admin/overview", headers=admin_headers)).json()["data"]

    assert data["contracts"]["byStatus"]["pilot"] == 1
    assert data["activePremiumGrants"] == {"purchase": 0, "adminGrant": 0}
    assert await db.scalar(select(Contract.price_cents)) == 0
