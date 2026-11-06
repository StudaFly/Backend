import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.exceptions import ConflictError, NotFoundError
from src.app.models.enums import AccountType, PremiumSource
from src.app.models.premium_grant import PremiumGrant
from src.app.models.user import User
from src.app.schemas.platform_admin import PremiumGrantCreate, PremiumGrantRead, PurchaseRead
from src.app.services import audit_service
from src.app.services.audit_service import RequestMeta

PREMIUM_PRICE_CENTS = 999


async def list_grants(db: AsyncSession, user_id: uuid.UUID) -> list[PremiumGrantRead]:
    grants = await db.scalars(
        select(PremiumGrant)
        .where(PremiumGrant.user_id == user_id)
        .order_by(PremiumGrant.created_at.desc())
    )
    return [PremiumGrantRead.model_validate(g) for g in grants]


async def grant(
    db: AsyncSession, actor: User, user: User, payload: PremiumGrantCreate, meta: RequestMeta
) -> PremiumGrantRead:
    if user.account_type != AccountType.STUDENT:
        raise ConflictError("Premium is for student accounts", code="NOT_A_STUDENT")
    if payload.ends_at and payload.ends_at <= datetime.now(UTC):
        raise ConflictError("endsAt must be in the future", code="INVALID_DATES")

    premium_grant = PremiumGrant(
        user_id=user.id,
        source=PremiumSource.ADMIN_GRANT,
        ends_at=payload.ends_at,
        reason=payload.reason,
        granted_by=actor.id,
    )
    db.add(premium_grant)
    await db.flush()
    audit_service.record(
        db,
        actor=actor,
        action="premium.grant",
        target_type="user",
        target_id=user.id,
        changes={
            "grant_id": str(premium_grant.id),
            "ends_at": payload.ends_at.isoformat() if payload.ends_at else None,
        },
        meta=meta,
    )
    await db.commit()
    await db.refresh(premium_grant)
    return PremiumGrantRead.model_validate(premium_grant)


async def revoke(
    db: AsyncSession,
    actor: User | None,
    user_id: uuid.UUID,
    grant_id: uuid.UUID,
    reason: str,
    meta: RequestMeta | None = None,
) -> PremiumGrantRead:
    premium_grant = await db.scalar(
        select(PremiumGrant).where(PremiumGrant.id == grant_id, PremiumGrant.user_id == user_id)
    )
    if not premium_grant:
        raise NotFoundError("Premium grant not found")
    if premium_grant.revoked_at:
        raise ConflictError("This grant is already revoked", code="ALREADY_REVOKED")

    premium_grant.revoked_at = datetime.now(UTC)
    premium_grant.revoked_by = actor.id if actor else None
    premium_grant.reason = reason
    audit_service.record(
        db,
        actor=actor,
        action="premium.revoke",
        target_type="user",
        target_id=user_id,
        changes={"grant_id": str(premium_grant.id), "source": premium_grant.source.value},
        meta=meta,
    )
    await db.commit()
    await db.refresh(premium_grant)
    return PremiumGrantRead.model_validate(premium_grant)


async def record_purchase(
    db: AsyncSession,
    user: User,
    stripe_payment_ref: str,
    amount_cents: int = PREMIUM_PRICE_CENTS,
    currency: str = "EUR",
) -> PremiumGrant:
    existing = await db.scalar(
        select(PremiumGrant).where(PremiumGrant.stripe_payment_ref == stripe_payment_ref)
    )
    if existing:
        return existing
    purchase = PremiumGrant(
        user_id=user.id,
        source=PremiumSource.PURCHASE,
        stripe_payment_ref=stripe_payment_ref,
        amount_cents=amount_cents,
        currency=currency,
    )
    db.add(purchase)
    await db.flush()
    audit_service.record(
        db,
        actor=None,
        action="premium.purchase",
        target_type="user",
        target_id=user.id,
        changes={"grant_id": str(purchase.id), "amount_cents": amount_cents},
    )
    await db.commit()
    return purchase


async def revoke_refunded_purchase(
    db: AsyncSession, stripe_payment_ref: str
) -> PremiumGrant | None:
    purchase = await db.scalar(
        select(PremiumGrant).where(
            PremiumGrant.stripe_payment_ref == stripe_payment_ref,
            PremiumGrant.source == PremiumSource.PURCHASE,
        )
    )
    if not purchase or purchase.revoked_at:
        return purchase
    await revoke(db, None, purchase.user_id, purchase.id, "refund")
    return purchase


async def list_purchases(
    db: AsyncSession, *, page: int, per_page: int
) -> tuple[list[PurchaseRead], int]:
    filters = [PremiumGrant.source == PremiumSource.PURCHASE]
    total = await db.scalar(select(func.count(PremiumGrant.id)).where(*filters))
    rows = await db.execute(
        select(PremiumGrant, User.email)
        .join(User, User.id == PremiumGrant.user_id)
        .where(*filters)
        .order_by(PremiumGrant.created_at.desc(), PremiumGrant.id)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    return [
        PurchaseRead(
            **PremiumGrantRead.model_validate(g).model_dump(),
            user_id=g.user_id,
            email=email,
            stripe_payment_ref=g.stripe_payment_ref,
        )
        for g, email in rows.all()
    ], total or 0


async def active_grant_counts(db: AsyncSession) -> dict[str, int]:
    now = datetime.now(UTC)
    rows = await db.execute(
        select(PremiumGrant.source, func.count(PremiumGrant.id))
        .where(
            PremiumGrant.revoked_at.is_(None),
            PremiumGrant.starts_at <= now,
            (PremiumGrant.ends_at.is_(None)) | (PremiumGrant.ends_at > now),
        )
        .group_by(PremiumGrant.source)
    )
    counts = {source.value: count for source, count in rows.all()}
    return {source.value: counts.get(source.value, 0) for source in PremiumSource}
