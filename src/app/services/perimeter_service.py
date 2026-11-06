import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.exceptions import ConflictError, NotFoundError
from src.app.core.zones import fully_covered_zones
from src.app.models.advisor_perimeter import AdvisorPerimeter
from src.app.models.enums import EnrollmentStatus
from src.app.models.mobility import Mobility
from src.app.models.mobility_advisor_override import MobilityAdvisorOverride
from src.app.models.organization_member import OrganizationMember
from src.app.models.student_enrollment import StudentEnrollment
from src.app.models.user import User
from src.app.schemas.org import PerimeterRead, PerimeterUpdate
from src.app.services import audit_service, organization_service
from src.app.services.audit_service import RequestMeta


async def member_countries(db: AsyncSession, member_id: uuid.UUID) -> list[str]:
    return sorted(
        await db.scalars(
            select(AdvisorPerimeter.country_code).where(AdvisorPerimeter.member_id == member_id)
        )
    )


def _perimeter_read(member_id: uuid.UUID, countries: list[str]) -> PerimeterRead:
    return PerimeterRead(
        member_id=member_id, countries=countries, zones=fully_covered_zones(set(countries))
    )


async def get_perimeter(
    db: AsyncSession, organization_id: uuid.UUID, member_id: uuid.UUID
) -> PerimeterRead:
    member = await db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.id == member_id,
            OrganizationMember.organization_id == organization_id,
        )
    )
    if not member:
        raise NotFoundError("Member not found")
    return _perimeter_read(member.id, await member_countries(db, member.id))


async def set_perimeter(
    db: AsyncSession,
    actor: User,
    organization_id: uuid.UUID,
    member_id: uuid.UUID,
    payload: PerimeterUpdate,
    meta: RequestMeta,
) -> PerimeterRead:
    organization = await organization_service.get_organization(db, organization_id, lock=True)
    member = await db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.id == member_id,
            OrganizationMember.organization_id == organization.id,
        )
    )
    if not member:
        raise NotFoundError("Member not found")
    if not member.is_active:
        raise ConflictError("This member is deactivated", code="MEMBER_INACTIVE")

    wanted = set(payload.countries)
    taken = {
        row.country_code: row
        for row in await db.scalars(
            select(AdvisorPerimeter).where(
                AdvisorPerimeter.organization_id == organization.id,
                AdvisorPerimeter.country_code.in_(wanted),
                AdvisorPerimeter.member_id != member.id,
            )
        )
    }
    if taken and not payload.reassign:
        raise ConflictError(
            f"Already in another member's perimeter: {', '.join(sorted(taken))}",
            code="COUNTRY_ALREADY_ASSIGNED",
        )
    for row in taken.values():
        await db.delete(row)

    current = set(await member_countries(db, member.id))
    removed, added = sorted(current - wanted), sorted(wanted - current)
    if removed:
        await db.execute(
            delete(AdvisorPerimeter).where(
                AdvisorPerimeter.member_id == member.id,
                AdvisorPerimeter.country_code.in_(removed),
            )
        )
    await db.flush()
    db.add_all(
        AdvisorPerimeter(organization_id=organization.id, member_id=member.id, country_code=code)
        for code in added
    )

    if added or removed:
        audit_service.record(
            db,
            actor=actor,
            action="perimeter.update",
            target_type="member",
            target_id=member.id,
            organization_id=organization.id,
            changes={
                "added": added,
                "removed": removed,
                "reassigned_from": {code: str(row.member_id) for code, row in taken.items()},
            },
            meta=meta,
        )
    await db.commit()
    return _perimeter_read(member.id, sorted(wanted))


async def _get_org_mobility(
    db: AsyncSession, organization_id: uuid.UUID, mobility_id: uuid.UUID
) -> Mobility:
    mobility = await db.scalar(
        select(Mobility)
        .join(StudentEnrollment, StudentEnrollment.student_id == Mobility.user_id)
        .where(
            Mobility.id == mobility_id,
            StudentEnrollment.organization_id == organization_id,
            StudentEnrollment.status == EnrollmentStatus.ACTIVE,
        )
    )
    if not mobility:
        raise NotFoundError("Mobility not found")
    return mobility


async def set_override(
    db: AsyncSession,
    actor: User,
    organization_id: uuid.UUID,
    mobility_id: uuid.UUID,
    member_id: uuid.UUID,
    meta: RequestMeta,
) -> None:
    mobility = await _get_org_mobility(db, organization_id, mobility_id)
    member = await db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.id == member_id,
            OrganizationMember.organization_id == organization_id,
        )
    )
    if not member:
        raise NotFoundError("Member not found")
    if not member.is_active:
        raise ConflictError("This member is deactivated", code="MEMBER_INACTIVE")

    override = await db.scalar(
        select(MobilityAdvisorOverride).where(MobilityAdvisorOverride.mobility_id == mobility.id)
    )
    previous = override.member_id if override else None
    if override:
        override.member_id = member.id
        override.set_by = actor.id
    else:
        db.add(
            MobilityAdvisorOverride(mobility_id=mobility.id, member_id=member.id, set_by=actor.id)
        )
    audit_service.record(
        db,
        actor=actor,
        action="assignment.set",
        target_type="mobility",
        target_id=mobility.id,
        organization_id=organization_id,
        changes={
            "member_id": [str(previous) if previous else None, str(member.id)],
        },
        meta=meta,
    )
    await db.commit()


async def clear_override(
    db: AsyncSession,
    actor: User,
    organization_id: uuid.UUID,
    mobility_id: uuid.UUID,
    meta: RequestMeta,
) -> None:
    mobility = await _get_org_mobility(db, organization_id, mobility_id)
    override = await db.scalar(
        select(MobilityAdvisorOverride).where(MobilityAdvisorOverride.mobility_id == mobility.id)
    )
    if not override:
        raise NotFoundError("This mobility has no manual assignment")

    await db.delete(override)
    audit_service.record(
        db,
        actor=actor,
        action="assignment.clear",
        target_type="mobility",
        target_id=mobility.id,
        organization_id=organization_id,
        changes={"member_id": [str(override.member_id), None]},
        meta=meta,
    )
    await db.commit()
