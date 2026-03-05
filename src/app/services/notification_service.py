from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


async def send_push(user_id: UUID, title: str, body: str) -> None:
    # TODO: send via FCM (Android) or APNs (iOS)
    raise NotImplementedError


async def send_email(to: str, subject: str, html_content: str) -> None:
    # TODO: send via AWS SES
    raise NotImplementedError


async def list_notifications(db: AsyncSession, user_id: UUID) -> list:
    # TODO: fetch user notifications, ordered by created_at desc
    raise NotImplementedError
