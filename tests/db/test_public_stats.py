"""Public landing stats counted on the real schema."""

from src.app.models.enums import AccountType

from tests.db.factories import make_destination, make_platform_admin, make_user


async def test_public_stats_count_only_students(api, db):
    await make_destination(db, country="Espagne", country_code="ES")
    await make_destination(db, country="Japon", country_code="JP")
    await make_user(db)
    await make_user(db)
    await make_user(db, AccountType.ORG_STAFF)
    await make_platform_admin(db)
    await db.commit()

    response = await api.get("/stats")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["students"] == 2
    assert data["destinations"] == 2
    assert data["countries"] == 2
