"""Premium entitlement: purchase, admin grant, organization contract, grandfathering (D5)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from src.app.models.enums import AccountType, ContractStatus, EnrollmentStatus
from src.app.services import entitlements, premium_service

from tests.db.factories import (
    auth_headers,
    make_contract,
    make_destination,
    make_enrollment,
    make_mobility,
    make_organization,
    make_platform_admin,
    make_user,
)


async def _premium(api, user) -> dict:
    response = await api.get("/users/me", headers=auth_headers(user))
    data = response.json()["data"]
    assert data["isPremium"] is data["premium"]["active"]
    return data["premium"]


@pytest.fixture
async def admin_headers(db):
    admin = await make_platform_admin(db)
    await db.commit()
    return auth_headers(admin, mfa=True)


async def test_a_new_student_is_free(api, db):
    student = await make_user(db)
    await db.commit()

    assert await _premium(api, student) == {"active": False, "source": None, "until": None}


async def test_admin_grant_and_revocation(api, db, admin_headers):
    student = await make_user(db)
    await db.commit()
    ends_at = (datetime.now(UTC) + timedelta(days=60)).isoformat()

    granted = await api.post(
        f"/admin/users/{student.id}/premium-grants",
        json={"endsAt": ends_at, "reason": "Ambassador"},
        headers=admin_headers,
    )
    premium = await _premium(api, student)
    grant_id = granted.json()["data"]["id"]
    no_reason = await api.delete(
        f"/admin/users/{student.id}/premium-grants/{grant_id}", headers=admin_headers
    )
    revoked = await api.delete(
        f"/admin/users/{student.id}/premium-grants/{grant_id}?reason=Ended", headers=admin_headers
    )
    detail = await api.get(f"/admin/users/{student.id}", headers=admin_headers)

    assert granted.status_code == 201
    assert premium["source"] == "admin_grant"
    assert premium["until"] == ends_at[:10]
    assert no_reason.status_code == 422
    assert revoked.json()["data"]["revokedAt"]
    assert (await _premium(api, student))["active"] is False
    assert len(detail.json()["data"]["premiumGrants"]) == 1


async def test_premium_is_only_granted_to_students(api, db, admin_headers):
    staff = await make_user(db, AccountType.ORG_STAFF)
    admin = await make_platform_admin(db)
    await db.commit()

    for user, expected in ((staff, 409), (admin, 403)):
        response = await api.post(
            f"/admin/users/{user.id}/premium-grants", json={"reason": "Test"}, headers=admin_headers
        )
        assert response.status_code == expected


async def test_purchase_then_refund(api, db, admin_headers):
    student = await make_user(db)
    await db.commit()

    purchase = await premium_service.record_purchase(db, student, "pi_123")
    again = await premium_service.record_purchase(db, student, "pi_123")
    premium = await _premium(api, student)
    purchases = await api.get("/admin/purchases", headers=admin_headers)
    await premium_service.revoke_refunded_purchase(db, "pi_123")

    assert again.id == purchase.id
    assert premium == {"active": True, "source": "purchase", "until": None}
    [listed] = purchases.json()["data"]
    assert (listed["amountCents"], listed["stripePaymentRef"]) == (999, "pi_123")
    assert (await _premium(api, student))["active"] is False


@pytest.mark.parametrize("status", [ContractStatus.ACTIVE, ContractStatus.PILOT])
async def test_an_enrolled_student_gets_premium_from_the_contract(api, db, status):
    organization = await make_organization(db)
    contract = await make_contract(db, organization, status)
    student = await make_user(db)
    await make_enrollment(db, organization, student)
    await db.commit()

    assert await _premium(api, student) == {
        "active": True,
        "source": "organization",
        "until": contract.end_date.isoformat(),
    }


async def test_no_premium_without_a_current_contract(api, db):
    organization = await make_organization(db)
    student = await make_user(db)
    await make_enrollment(db, organization, student)
    await db.commit()

    assert (await _premium(api, student))["active"] is False


async def test_a_purchase_outlasts_the_organization(api, db):
    organization = await make_organization(db)
    await make_contract(db, organization)
    student = await make_user(db)
    await make_enrollment(db, organization, student)
    await db.commit()
    await premium_service.record_purchase(db, student, "pi_both")

    assert (await _premium(api, student))["source"] == "purchase"


@pytest.fixture
async def ended_contract(db):
    organization = await make_organization(db)
    start = date.today() - timedelta(days=400)
    end = date.today() - timedelta(days=10)
    await make_contract(db, organization, ContractStatus.EXPIRED, start, end)
    return organization, datetime.combine(end - timedelta(days=60), datetime.min.time(), UTC)


async def _student_with_mobility(db, organization, created_at, **mobility_fields):
    student = await make_user(db)
    enrollment = await make_enrollment(db, organization, student)
    enrollment.joined_at = created_at - timedelta(days=30)
    mobility = await make_mobility(db, student, await make_destination(db))
    mobility.created_at = created_at
    for key, value in mobility_fields.items():
        setattr(mobility, key, value)
    await db.commit()
    return student, enrollment


async def test_the_ongoing_mobility_keeps_premium_after_the_contract(api, db, ended_contract):
    organization, during_contract = ended_contract
    return_date = date.today() + timedelta(days=120)
    student, _ = await _student_with_mobility(
        db, organization, during_contract, return_date=return_date
    )

    assert await _premium(api, student) == {
        "active": True,
        "source": "grandfathered",
        "until": return_date.isoformat(),
    }


@pytest.mark.parametrize(
    "mobility_fields",
    [{"status": "completed"}, {"return_date": date.today() - timedelta(days=1)}],
    ids=["completed", "returned"],
)
async def test_premium_ends_with_the_mobility(api, db, ended_contract, mobility_fields):
    organization, during_contract = ended_contract
    student, _ = await _student_with_mobility(db, organization, during_contract, **mobility_fields)

    assert (await _premium(api, student))["active"] is False


async def test_a_mobility_created_after_the_contract_is_not_covered(api, db, ended_contract):
    organization, _ = ended_contract
    student, _ = await _student_with_mobility(db, organization, datetime.now(UTC))

    assert (await _premium(api, student))["active"] is False


@pytest.mark.parametrize(
    ("status", "expected"), [(EnrollmentStatus.LEFT, False), (EnrollmentStatus.REVOKED, True)]
)
async def test_leaving_voluntarily_drops_grandfathering(api, db, ended_contract, status, expected):
    organization, during_contract = ended_contract
    student, enrollment = await _student_with_mobility(db, organization, during_contract)
    enrollment.status = status
    enrollment.ended_at = datetime.now(UTC)
    await db.commit()

    assert (await _premium(api, student))["active"] is expected


async def test_batch_computation_matches_single_lookups(db, ended_contract):
    organization, during_contract = ended_contract
    covered, _ = await _student_with_mobility(db, organization, during_contract)
    free = await make_user(db)
    await db.commit()

    batch = await entitlements.premium_for_users(db, [covered.id, free.id])

    assert batch[covered.id] == await entitlements.premium_for(db, covered.id)
    assert batch[free.id] == entitlements.NO_PREMIUM
