import uuid

from sqlalchemy import Select, and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.app.authz.actor import Actor
from src.app.models.advisor_perimeter import AdvisorPerimeter
from src.app.models.destination import Destination
from src.app.models.enums import EnrollmentStatus, OrgRole
from src.app.models.mobility import Mobility
from src.app.models.mobility_advisor_override import MobilityAdvisorOverride
from src.app.models.organization_member import OrganizationMember
from src.app.models.student_enrollment import StudentEnrollment

COMPLETED_MOBILITY = "completed"


def assignments(organization_id: uuid.UUID):
    override_member = aliased(OrganizationMember)
    perimeter_member = aliased(OrganizationMember)
    return (
        select(
            Mobility.id.label("mobility_id"),
            Mobility.user_id.label("student_id"),
            Destination.country_code.label("country_code"),
            override_member.id.label("override_member_id"),
            perimeter_member.id.label("perimeter_member_id"),
            func.coalesce(override_member.id, perimeter_member.id).label("member_id"),
        )
        .join(Destination, Destination.id == Mobility.destination_id)
        .join(
            StudentEnrollment,
            and_(
                StudentEnrollment.student_id == Mobility.user_id,
                StudentEnrollment.organization_id == organization_id,
                StudentEnrollment.status == EnrollmentStatus.ACTIVE,
            ),
        )
        .outerjoin(MobilityAdvisorOverride, MobilityAdvisorOverride.mobility_id == Mobility.id)
        .outerjoin(
            override_member,
            and_(
                override_member.id == MobilityAdvisorOverride.member_id,
                override_member.organization_id == organization_id,
                override_member.is_active,
            ),
        )
        .outerjoin(
            AdvisorPerimeter,
            and_(
                AdvisorPerimeter.organization_id == organization_id,
                AdvisorPerimeter.country_code == Destination.country_code,
            ),
        )
        .outerjoin(
            perimeter_member,
            and_(perimeter_member.id == AdvisorPerimeter.member_id, perimeter_member.is_active),
        )
        .where(Mobility.status != COMPLETED_MOBILITY)
        .subquery()
    )


def visible_student_ids(actor: Actor) -> Select:
    organization_id = actor.organization_id
    if actor.org_role == OrgRole.MANAGER:
        return select(StudentEnrollment.student_id).where(
            StudentEnrollment.organization_id == organization_id,
            StudentEnrollment.status == EnrollmentStatus.ACTIVE,
        )
    assigned = assignments(organization_id)
    return (
        select(assigned.c.student_id).where(assigned.c.member_id == actor.membership.id).distinct()
    )


async def can_view_student(db: AsyncSession, actor: Actor, student_id: uuid.UUID) -> bool:
    visible = visible_student_ids(actor).subquery()
    return bool(await db.scalar(select(exists().where(visible.c.student_id == student_id))))
