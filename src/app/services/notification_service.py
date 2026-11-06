"""In-app notifications, Expo push delivery and the daily deadline reminders.

A notification is always stored in the database (the in-app list); push is sent on top of it
when the user kept notifications enabled and has at least one registered device.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.config import settings
from src.app.core.exceptions import NotFoundError
from src.app.models.enums import AccountType, NotificationType, PushPlatform, UserStatus
from src.app.models.mobility import Mobility
from src.app.models.notification import Notification
from src.app.models.push_token import PushToken
from src.app.models.task import Task
from src.app.models.user import User
from src.app.schemas.notification import NotificationList, NotificationRead

logger = logging.getLogger(__name__)

EXPO_BATCH_SIZE = 100
DUE_SOON_DAYS = 7
OVERDUE_LOOKBACK_DAYS = 7


# --- In-app list -------------------------------------------------------------------------------


async def list_notifications(
    db: AsyncSession, user_id: UUID, *, unread_only: bool = False, limit: int = 50, offset: int = 0
) -> NotificationList:
    query = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    rows = await db.scalars(
        query.order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return NotificationList(
        items=[NotificationRead.model_validate(n) for n in rows],
        unread_count=await unread_count(db, user_id),
    )


async def unread_count(db: AsyncSession, user_id: UUID) -> int:
    return await db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
    )


async def _get_for_user(db: AsyncSession, user_id: UUID, notification_id: UUID) -> Notification:
    notification = await db.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user_id
        )
    )
    if not notification:
        raise NotFoundError("Notification not found")
    return notification


async def mark_read(db: AsyncSession, user_id: UUID, notification_id: UUID) -> NotificationRead:
    notification = await _get_for_user(db, user_id, notification_id)
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(notification)
    return NotificationRead.model_validate(notification)


async def mark_all_read(db: AsyncSession, user_id: UUID) -> int:
    result = await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        .values(is_read=True, read_at=datetime.now(UTC))
    )
    await db.commit()
    return result.rowcount


async def delete_notification(db: AsyncSession, user_id: UUID, notification_id: UUID) -> None:
    notification = await _get_for_user(db, user_id, notification_id)
    await db.delete(notification)
    await db.commit()


# --- Creation ----------------------------------------------------------------------------------


async def notify(
    db: AsyncSession,
    user_id: UUID,
    type: NotificationType,
    title: str,
    body: str | None = None,
    data: dict[str, Any] | None = None,
    *,
    dedupe_key: str | None = None,
) -> Notification | None:
    """Add a notification to the current transaction (the caller commits).

    With a dedupe_key, a notification already sent to this user with the same key is not
    created twice and None is returned. Push is not sent here: call `deliver` after the commit.
    """
    values = {
        "user_id": user_id,
        "type": type.value,
        "title": title,
        "body": body,
        "data": data or {},
        "dedupe_key": dedupe_key,
    }
    statement = insert(Notification).values(**values).returning(Notification)
    if dedupe_key is not None:
        statement = statement.on_conflict_do_nothing(
            index_elements=["user_id", "dedupe_key"],
            index_where=Notification.dedupe_key.is_not(None),
        )
    return (await db.execute(statement)).scalar_one_or_none()


# --- Push --------------------------------------------------------------------------------------


async def register_push_token(
    db: AsyncSession, user_id: UUID, token: str, platform: PushPlatform
) -> None:
    """Attach a device to the user. A device that changes account moves to the new user."""
    statement = insert(PushToken).values(user_id=user_id, token=token, platform=platform.value)
    statement = statement.on_conflict_do_update(
        index_elements=["token"],
        set_={"user_id": user_id, "platform": platform.value, "last_seen_at": func.now()},
    )
    await db.execute(statement)
    await db.commit()


async def unregister_push_token(db: AsyncSession, user_id: UUID, token: str) -> None:
    await db.execute(
        delete(PushToken).where(PushToken.user_id == user_id, PushToken.token == token)
    )
    await db.commit()


async def _post_to_expo(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if settings.EXPO_ACCESS_TOKEN:
        headers["Authorization"] = f"Bearer {settings.EXPO_ACCESS_TOKEN}"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(settings.EXPO_PUSH_URL, json=messages, headers=headers)
        response.raise_for_status()
        return response.json().get("data", [])


@dataclass
class DeliveryReport:
    sent: int = 0
    failed: int = 0
    removed_tokens: int = 0


async def deliver(db: AsyncSession, notifications: Iterable[Notification]) -> DeliveryReport:
    """Send the push for already committed notifications. Never raises: push is best effort."""
    report = DeliveryReport()
    notifications = [n for n in notifications if n is not None]
    if not settings.PUSH_NOTIFICATIONS_ENABLED or not notifications:
        return report

    user_ids = {n.user_id for n in notifications}
    rows = await db.execute(
        select(PushToken.user_id, PushToken.token)
        .join(User, User.id == PushToken.user_id)
        .where(PushToken.user_id.in_(user_ids), User.enable_notifications.is_(True))
    )
    tokens: dict[UUID, list[str]] = {}
    for user_id, token in rows:
        tokens.setdefault(user_id, []).append(token)

    messages = [
        {
            "to": token,
            "title": n.title,
            "body": n.body or "",
            "sound": "default",
            "data": {**n.data, "notificationId": str(n.id), "type": n.type},
        }
        for n in notifications
        for token in tokens.get(n.user_id, [])
    ]

    dead_tokens: set[str] = set()
    for start in range(0, len(messages), EXPO_BATCH_SIZE):
        batch = messages[start : start + EXPO_BATCH_SIZE]
        try:
            tickets = await _post_to_expo(batch)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Expo push request failed (%s): %s", type(exc).__name__, exc)
            report.failed += len(batch)
            continue
        for message, ticket in zip(batch, tickets, strict=False):
            if ticket.get("status") == "ok":
                report.sent += 1
                continue
            report.failed += 1
            if (ticket.get("details") or {}).get("error") == "DeviceNotRegistered":
                dead_tokens.add(message["to"])
            else:
                logger.warning("Expo push rejected: %s", ticket.get("message"))

    if dead_tokens:
        await db.execute(delete(PushToken).where(PushToken.token.in_(dead_tokens)))
        await db.commit()
        report.removed_tokens = len(dead_tokens)
    return report


async def send_email(to: str, subject: str, html_content: str) -> None:
    # TODO: send via AWS SES (separate ticket)
    raise NotImplementedError


# --- Deadline reminders (daily maintenance) ----------------------------------------------------


def _reminder(task: Task, days_left: int) -> tuple[NotificationType, str, str, str] | None:
    """(type, stage, title, body) of the reminder due for this task today, if any."""
    if days_left < -OVERDUE_LOOKBACK_DAYS or days_left > DUE_SOON_DAYS:
        return None
    if days_left < 0:
        late = -days_left
        return (
            NotificationType.TASK_OVERDUE,
            "overdue",
            "Tâche en retard",
            f"« {task.title} » devait être faite il y a {late} jour{'s' if late > 1 else ''}.",
        )
    if days_left == 0:
        return (
            NotificationType.TASK_DUE_TODAY,
            "today",
            "Échéance aujourd'hui",
            f"« {task.title} » est à faire aujourd'hui.",
        )
    if days_left == 1:
        return (
            NotificationType.TASK_DUE_SOON,
            "tomorrow",
            "Échéance demain",
            f"« {task.title} » est à faire pour demain.",
        )
    return (
        NotificationType.TASK_DUE_SOON,
        "week",
        "Échéance proche",
        f"« {task.title} » est à faire dans {days_left} jours.",
    )


async def send_deadline_reminders(db: AsyncSession, today: date | None = None) -> int:
    """Create the reminders for incomplete tasks due within a week or recently overdue.

    Idempotent: each stage (week, tomorrow, today, overdue) is sent once per task and
    deadline, so running the job twice a day or after a missed day does not spam anyone.
    """
    today = today or date.today()
    rows = await db.execute(
        select(Task, Mobility.user_id)
        .join(Mobility, Mobility.id == Task.mobility_id)
        .join(User, User.id == Mobility.user_id)
        .where(
            Task.is_completed.is_(False),
            Task.deadline.is_not(None),
            Task.deadline >= today - timedelta(days=OVERDUE_LOOKBACK_DAYS),
            Task.deadline <= today + timedelta(days=DUE_SOON_DAYS),
            Mobility.status != "completed",
            User.status == UserStatus.ACTIVE,
            User.account_type == AccountType.STUDENT,
        )
    )
    created: list[Notification] = []
    for task, user_id in rows:
        reminder = _reminder(task, (task.deadline - today).days)
        if reminder is None:
            continue
        type_, stage, title, body = reminder
        notification = await notify(
            db,
            user_id,
            type_,
            title,
            body,
            {"taskId": str(task.id), "mobilityId": str(task.mobility_id)},
            dedupe_key=f"task:{task.id}:{task.deadline.isoformat()}:{stage}",
        )
        if notification is not None:
            created.append(notification)
    await db.commit()
    await deliver(db, created)
    return len(created)
