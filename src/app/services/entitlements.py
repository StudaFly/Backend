import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.contract import Contract
from src.app.models.enums import ContractStatus, EnrollmentStatus, PremiumSource
from src.app.models.mobility import Mobility
from src.app.models.premium_grant import PremiumGrant
from src.app.models.student_enrollment import StudentEnrollment

ORGANIZATION = "organization"
GRANDFATHERED = "grandfathered"
CURRENT_CONTRACT_STATUSES = (ContractStatus.PILOT, ContractStatus.ACTIVE)
_PRIORITY = {
    PremiumSource.PURCHASE.value: 0,
    PremiumSource.ADMIN_GRANT.value: 1,
    ORGANIZATION: 2,
    GRANDFATHERED: 3,
}


@dataclass(frozen=True)
class Entitlement:
    active: bool
    source: str | None = None
    until: date | None = None


NO_PREMIUM = Entitlement(active=False)


def _best(candidates: list[tuple[str, date | None]]) -> Entitlement:
    if not candidates:
        return NO_PREMIUM
    source, until = min(
        candidates, key=lambda c: (-(c[1] or date.max).toordinal(), _PRIORITY[c[0]])
    )
    return Entitlement(active=True, source=source, until=until)


async def premium_for_users(
    db: AsyncSession, user_ids: list[uuid.UUID], now: datetime | None = None
) -> dict[uuid.UUID, Entitlement]:
    if not user_ids:
        return {}
    now = now or datetime.now(UTC)
    today = now.date()
    candidates: dict[uuid.UUID, list[tuple[str, date | None]]] = {uid: [] for uid in user_ids}

    grants = await db.execute(
        select(PremiumGrant.user_id, PremiumGrant.source, PremiumGrant.ends_at).where(
            PremiumGrant.user_id.in_(user_ids),
            PremiumGrant.revoked_at.is_(None),
            PremiumGrant.starts_at <= now,
            or_(PremiumGrant.ends_at.is_(None), PremiumGrant.ends_at > now),
        )
    )
    for user_id, source, ends_at in grants.all():
        candidates[user_id].append((source.value, ends_at.date() if ends_at else None))

    organization = await db.execute(
        select(StudentEnrollment.student_id, Contract.end_date)
        .join(Contract, Contract.organization_id == StudentEnrollment.organization_id)
        .where(
            StudentEnrollment.student_id.in_(user_ids),
            StudentEnrollment.status == EnrollmentStatus.ACTIVE,
            Contract.status.in_(CURRENT_CONTRACT_STATUSES),
            Contract.start_date <= today,
            Contract.end_date >= today,
        )
    )
    for user_id, end_date in organization.all():
        candidates[user_id].append((ORGANIZATION, end_date))

    created_on = func.date(Mobility.created_at)
    grandfathered = await db.execute(
        select(Mobility.user_id, Mobility.return_date)
        .join(StudentEnrollment, StudentEnrollment.student_id == Mobility.user_id)
        .join(Contract, Contract.organization_id == StudentEnrollment.organization_id)
        .where(
            Mobility.user_id.in_(user_ids),
            Mobility.status != "completed",
            or_(Mobility.return_date.is_(None), Mobility.return_date >= today),
            StudentEnrollment.status.in_((EnrollmentStatus.ACTIVE, EnrollmentStatus.REVOKED)),
            created_on >= Contract.start_date,
            created_on <= Contract.end_date,
            ~and_(
                Contract.status.in_(CURRENT_CONTRACT_STATUSES),
                Contract.start_date <= today,
                Contract.end_date >= today,
            ),
            func.date(StudentEnrollment.joined_at) <= Contract.end_date,
            or_(
                StudentEnrollment.ended_at.is_(None),
                func.date(StudentEnrollment.ended_at) >= Contract.start_date,
            ),
        )
    )
    for user_id, return_date in grandfathered.all():
        candidates[user_id].append((GRANDFATHERED, return_date))

    return {user_id: _best(options) for user_id, options in candidates.items()}


async def premium_for(db: AsyncSession, user_id: uuid.UUID) -> Entitlement:
    return (await premium_for_users(db, [user_id]))[user_id]
