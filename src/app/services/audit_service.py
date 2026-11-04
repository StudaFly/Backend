import uuid
from dataclasses import dataclass
from datetime import datetime

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.audit_log import AuditLog
from src.app.models.user import User

CLI_ACTOR = "cli"

_REDACTED_KEYS = {
    "password",
    "password_hash",
    "new_password",
    "mfa_secret",
    "mfa_backup_codes",
    "backup_codes",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "email",
    "phone",
    "reason",
    "suspended_reason",
}


@dataclass(frozen=True)
class RequestMeta:
    ip: str | None = None
    user_agent: str | None = None


def get_request_meta(request: Request) -> RequestMeta:
    user_agent = request.headers.get("user-agent")
    return RequestMeta(
        ip=request.client.host if request.client else None,
        user_agent=user_agent[:255] if user_agent else None,
    )


def scrub(changes: dict) -> dict:
    clean = {}
    for key, value in changes.items():
        if key.lower() in _REDACTED_KEYS:
            continue
        clean[key] = scrub(value) if isinstance(value, dict) else value
    return clean


def record(
    db: AsyncSession,
    *,
    actor: User | None,
    action: str,
    target_type: str,
    target_id: uuid.UUID | None,
    organization_id: uuid.UUID | None = None,
    changes: dict | None = None,
    meta: RequestMeta | None = None,
) -> AuditLog:
    meta = meta or RequestMeta()
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        actor_account_type=actor.account_type.value if actor else CLI_ACTOR,
        action=action,
        target_type=target_type,
        target_id=target_id,
        organization_id=organization_id,
        changes=scrub(changes or {}),
        ip=meta.ip,
        user_agent=meta.user_agent,
    )
    db.add(entry)
    return entry


async def list_entries(
    db: AsyncSession,
    *,
    page: int,
    per_page: int,
    actor_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    action: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> tuple[list[AuditLog], int]:
    filters = []
    if actor_id:
        filters.append(AuditLog.actor_id == actor_id)
    if target_type:
        filters.append(AuditLog.target_type == target_type)
    if target_id:
        filters.append(AuditLog.target_id == target_id)
    if organization_id:
        filters.append(AuditLog.organization_id == organization_id)
    if action:
        filters.append(AuditLog.action == action)
    if since:
        filters.append(AuditLog.created_at >= since)
    if until:
        filters.append(AuditLog.created_at < until)

    total = await db.scalar(select(func.count(AuditLog.id)).where(*filters))
    entries = await db.scalars(
        select(AuditLog)
        .where(*filters)
        .order_by(AuditLog.created_at.desc(), AuditLog.id)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    return list(entries), total or 0
