import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.config import settings
from src.app.core.exceptions import ConflictError, ForbiddenError, StudaFlyException
from src.app.models.audit_log import AuditLog
from src.app.models.document import Document
from src.app.models.enums import AccountType, InvitationStatus, UserStatus
from src.app.models.invitation import Invitation
from src.app.models.mobility import Mobility
from src.app.models.organization_member import OrganizationMember
from src.app.models.user import User
from src.app.services import audit_service, auth_service, organization_service, storage_service
from src.app.services.audit_service import RequestMeta

logger = logging.getLogger(__name__)


async def _ensure_not_last_manager(db: AsyncSession, user: User) -> None:
    member = await db.scalar(
        select(OrganizationMember).where(OrganizationMember.user_id == user.id)
    )
    if member:
        organization = await organization_service.get_organization(
            db, member.organization_id, lock=True
        )
        await organization_service.ensure_another_active_manager(db, organization, member)


async def schedule_deletion(
    db: AsyncSession, actor: User, user: User, meta: RequestMeta
) -> datetime:
    previous = user.status
    if previous == UserStatus.PENDING_DELETION:
        raise ConflictError("This account is already scheduled for deletion", code="INVALID_STATUS")
    await _ensure_not_last_manager(db, user)

    scheduled_at = datetime.now(UTC) + timedelta(days=settings.ACCOUNT_DELETION_DELAY_DAYS)
    user.status = UserStatus.PENDING_DELETION
    user.deletion_scheduled_at = scheduled_at
    await auth_service.revoke_all_sessions(user)
    audit_service.record(
        db,
        actor=actor,
        action="user.schedule_deletion",
        target_type="user",
        target_id=user.id,
        changes={
            "status": [previous.value, UserStatus.PENDING_DELETION.value],
            "deletion_scheduled_at": scheduled_at.isoformat(),
        },
        meta=meta,
    )
    await db.commit()
    return scheduled_at


async def request_own_deletion(db: AsyncSession, user: User, meta: RequestMeta) -> datetime:
    if user.account_type == AccountType.PLATFORM_ADMIN:
        raise ForbiddenError("Platform admins are removed with the CLI")
    return await schedule_deletion(db, user, user, meta)


@dataclass
class PurgeReport:
    purged: int = 0
    skipped: list[str] = field(default_factory=list)


async def _purge(db: AsyncSession, user: User) -> None:
    await _ensure_not_last_manager(db, user)
    file_urls = await db.scalars(
        select(Document.file_url)
        .join(Mobility, Mobility.id == Document.mobility_id)
        .where(Mobility.user_id == user.id)
    )
    for file_url in file_urls:
        await storage_service.delete_file(file_url)
    await db.execute(delete(Invitation).where(func.lower(Invitation.email) == user.email.lower()))
    audit_service.record(db, actor=None, action="user.purge", target_type="user", target_id=user.id)
    await db.delete(user)
    await db.commit()


async def purge_due_accounts(db: AsyncSession, now: datetime | None = None) -> PurgeReport:
    now = now or datetime.now(UTC)
    report = PurgeReport()
    due = list(
        await db.scalars(
            select(User.id).where(
                User.status == UserStatus.PENDING_DELETION,
                User.deletion_scheduled_at <= now,
            )
        )
    )
    for user_id in due:
        user = await db.get(User, user_id)
        try:
            await _purge(db, user)
            report.purged += 1
        except (StudaFlyException, NotImplementedError) as exc:
            await db.rollback()
            reason = exc.code if isinstance(exc, StudaFlyException) else "STORAGE_UNAVAILABLE"
            report.skipped.append(f"{user_id}: {reason}")
            logger.warning("Account %s not purged: %s", user_id, reason)
    return report


async def purge_audit_logs(db: AsyncSession, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    result = await db.execute(
        delete(AuditLog).where(
            AuditLog.created_at < now - timedelta(days=settings.AUDIT_RETENTION_DAYS)
        )
    )
    await db.commit()
    return result.rowcount or 0


async def expire_invitations(db: AsyncSession, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    result = await db.execute(
        update(Invitation)
        .where(Invitation.status == InvitationStatus.PENDING, Invitation.expires_at <= now)
        .values(status=InvitationStatus.EXPIRED)
    )
    await db.commit()
    return result.rowcount or 0
