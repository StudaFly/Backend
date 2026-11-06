from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.destination import Destination
from src.app.models.document import Document
from src.app.models.invitation import Invitation
from src.app.models.mobility import Mobility
from src.app.models.organization import Organization
from src.app.models.organization_member import OrganizationMember
from src.app.models.premium_grant import PremiumGrant
from src.app.models.student_enrollment import StudentEnrollment
from src.app.models.student_note import StudentNote
from src.app.models.task import Task
from src.app.models.user import User
from src.app.services import entitlements


def _iso(value) -> str | None:
    return value.isoformat() if value else None


async def export_user(db: AsyncSession, user: User) -> dict:
    mobilities = []
    rows = await db.execute(
        select(Mobility, Destination)
        .join(Destination, Destination.id == Mobility.destination_id)
        .where(Mobility.user_id == user.id)
        .order_by(Mobility.created_at)
    )
    for mobility, destination in rows.all():
        tasks = await db.scalars(
            select(Task).where(Task.mobility_id == mobility.id).order_by(Task.deadline, Task.title)
        )
        documents = await db.scalars(select(Document).where(Document.mobility_id == mobility.id))
        mobilities.append(
            {
                "id": str(mobility.id),
                "type": mobility.type,
                "status": mobility.status,
                "destination": {"city": destination.city, "country": destination.country},
                "departure_date": _iso(mobility.departure_date),
                "return_date": _iso(mobility.return_date),
                "school": mobility.school,
                "created_at": _iso(mobility.created_at),
                "tasks": [
                    {
                        "title": t.title,
                        "description": t.description,
                        "category": t.category,
                        "deadline": _iso(t.deadline),
                        "is_completed": t.is_completed,
                        "priority": t.priority,
                    }
                    for t in tasks
                ],
                "documents": [
                    {"category": d.category, "uploaded_at": _iso(d.uploaded_at)} for d in documents
                ],
            }
        )

    organizations = dict((await db.execute(select(Organization.id, Organization.name))).all())
    enrollments = await db.scalars(
        select(StudentEnrollment)
        .where(StudentEnrollment.student_id == user.id)
        .order_by(StudentEnrollment.joined_at)
    )
    memberships = await db.scalars(
        select(OrganizationMember).where(OrganizationMember.user_id == user.id)
    )
    notes = await db.scalars(
        select(StudentNote)
        .where(StudentNote.student_id == user.id)
        .order_by(StudentNote.created_at)
    )
    grants = await db.scalars(
        select(PremiumGrant)
        .where(PremiumGrant.user_id == user.id)
        .order_by(PremiumGrant.created_at)
    )
    invitations = await db.scalars(
        select(Invitation)
        .where(func.lower(Invitation.email) == user.email.lower())
        .order_by(Invitation.created_at)
    )
    premium = await entitlements.premium_for(db, user.id)

    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "profile": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "phone": user.phone,
            "avatar_emoji": user.avatar_emoji,
            "account_type": user.account_type.value,
            "email_verified": user.email_verified,
            "enable_notifications": user.enable_notifications,
            "created_at": _iso(user.created_at),
            "last_login_at": _iso(user.last_login_at),
        },
        "premium": {
            "active": premium.active,
            "source": premium.source,
            "until": _iso(premium.until),
        },
        "premium_grants": [
            {
                "source": g.source.value,
                "amount_cents": g.amount_cents,
                "currency": g.currency,
                "starts_at": _iso(g.starts_at),
                "ends_at": _iso(g.ends_at),
                "revoked_at": _iso(g.revoked_at),
            }
            for g in grants
        ],
        "mobilities": mobilities,
        "organizations": [
            {
                "organization": organizations.get(e.organization_id),
                "status": e.status.value,
                "source": e.source.value,
                "joined_at": _iso(e.joined_at),
                "ended_at": _iso(e.ended_at),
            }
            for e in enrollments
        ],
        "staff_memberships": [
            {
                "organization": organizations.get(m.organization_id),
                "org_role": m.org_role.value,
                "is_active": m.is_active,
            }
            for m in memberships
        ],
        "notes_written_about_you": [
            {
                "organization": organizations.get(n.organization_id),
                "body": n.body,
                "created_at": _iso(n.created_at),
            }
            for n in notes
        ],
        "invitations": [
            {
                "organization": organizations.get(i.organization_id),
                "kind": i.kind.value,
                "status": i.status.value,
                "created_at": _iso(i.created_at),
            }
            for i in invitations
        ],
    }
