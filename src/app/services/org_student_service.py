import uuid
from datetime import date

from sqlalchemy import Integer, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.authz.actor import Actor
from src.app.authz.scopes import (
    COMPLETED_MOBILITY,
    assignments,
    can_view_student,
    visible_student_ids,
)
from src.app.core.exceptions import NotFoundError
from src.app.core.zones import COUNTRY_ZONES
from src.app.models.destination import Destination
from src.app.models.document import Document
from src.app.models.enums import EnrollmentStatus, OrgRole
from src.app.models.mobility import Mobility
from src.app.models.organization_member import OrganizationMember
from src.app.models.student_enrollment import StudentEnrollment
from src.app.models.student_note import StudentNote
from src.app.models.task import Task
from src.app.models.user import User
from src.app.schemas.org import (
    AdvisorRef,
    CategoryProgress,
    DocumentStatus,
    FollowUp,
    NoteRead,
    StudentDetail,
    StudentListItem,
    StudentMobility,
    StudentMobilityDetail,
)

DEFAULT_PROGRESS_THRESHOLD = 50
DEFAULT_ALERT_DAYS = 30


def follow_up(mobility: StudentMobility | None, settings: dict, today: date) -> FollowUp | None:
    if mobility is None:
        return None
    threshold = settings.get("alert_threshold") or {}
    progress_below = threshold.get("progress_below", DEFAULT_PROGRESS_THRESHOLD)
    days_before = threshold.get("days_before_departure", DEFAULT_ALERT_DAYS)
    if (mobility.departure_date - today).days <= days_before and mobility.progress < progress_below:
        return "danger"
    if mobility.overdue_tasks:
        return "warning"
    return "ok"


async def _task_stats(
    db: AsyncSession, mobility_ids: list[uuid.UUID], today: date
) -> dict[uuid.UUID, tuple[int, int, int]]:
    if not mobility_ids:
        return {}
    rows = await db.execute(
        select(
            Task.mobility_id,
            func.count(Task.id),
            func.sum(case((Task.is_completed, 1), else_=0)).cast(Integer),
            func.sum(case(((~Task.is_completed) & (Task.deadline < today), 1), else_=0)).cast(
                Integer
            ),
        )
        .where(Task.mobility_id.in_(mobility_ids))
        .group_by(Task.mobility_id)
    )
    return {
        mobility_id: (total, done or 0, overdue or 0)
        for mobility_id, total, done, overdue in rows.all()
    }


async def _advisor_names(db: AsyncSession, member_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not member_ids:
        return {}
    rows = await db.execute(
        select(OrganizationMember.id, User.name)
        .join(User, User.id == OrganizationMember.user_id)
        .where(OrganizationMember.id.in_(member_ids))
    )
    return dict(rows.all())


async def _mobilities(
    db: AsyncSession,
    organization_id: uuid.UUID,
    student_ids: list[uuid.UUID],
    today: date,
    *,
    include_completed: bool = False,
) -> dict[uuid.UUID, list[StudentMobility]]:
    if not student_ids:
        return {}
    assigned = assignments(organization_id)
    query = (
        select(Mobility, Destination, assigned.c.member_id, assigned.c.override_member_id)
        .join(Destination, Destination.id == Mobility.destination_id)
        .outerjoin(assigned, assigned.c.mobility_id == Mobility.id)
        .where(Mobility.user_id.in_(student_ids))
        .order_by(Mobility.departure_date)
    )
    if not include_completed:
        query = query.where(Mobility.status != COMPLETED_MOBILITY)
    rows = (await db.execute(query)).all()

    stats = await _task_stats(db, [m.id for m, *_ in rows], today)
    names = await _advisor_names(db, {member_id for _, _, member_id, _ in rows if member_id})
    result: dict[uuid.UUID, list[StudentMobility]] = {}
    for mobility, destination, member_id, override_member_id in rows:
        total, done, overdue = stats.get(mobility.id, (0, 0, 0))
        result.setdefault(mobility.user_id, []).append(
            StudentMobility(
                id=mobility.id,
                type=mobility.type,
                status=mobility.status,
                departure_date=mobility.departure_date,
                return_date=mobility.return_date,
                city=destination.city,
                country=destination.country,
                country_code=destination.country_code,
                advisor=AdvisorRef(member_id=member_id, name=names[member_id])
                if member_id
                else None,
                assignment=("override" if override_member_id else "perimeter")
                if member_id
                else None,
                tasks_done=done,
                tasks_total=total,
                overdue_tasks=overdue,
                progress=round(done * 100 / total) if total else 0,
            )
        )
    return result


def _current(mobilities: list[StudentMobility], actor: Actor) -> StudentMobility | None:
    active = [m for m in mobilities if m.status != COMPLETED_MOBILITY]
    if actor.org_role == OrgRole.ADVISOR:
        mine = [m for m in active if m.advisor and m.advisor.member_id == actor.membership.id]
        active = mine or active
    return active[0] if active else None


async def list_students(
    db: AsyncSession,
    actor: Actor,
    *,
    page: int,
    per_page: int,
    q: str | None = None,
    status: FollowUp | None = None,
    zone: str | None = None,
    advisor_id: uuid.UUID | None = None,
    unassigned: bool = False,
    today: date | None = None,
) -> tuple[list[StudentListItem], int]:
    today = today or date.today()
    visible = visible_student_ids(actor).subquery()
    query = (
        select(User, StudentEnrollment.joined_at)
        .join(StudentEnrollment, StudentEnrollment.student_id == User.id)
        .where(
            StudentEnrollment.organization_id == actor.organization_id,
            StudentEnrollment.status == EnrollmentStatus.ACTIVE,
            User.id.in_(select(visible.c.student_id)),
        )
        .order_by(User.name, User.id)
    )
    if q:
        pattern = f"%{q}%"
        query = query.where(or_(User.name.ilike(pattern), User.email.ilike(pattern)))
    rows = (await db.execute(query)).all()

    mobilities = await _mobilities(db, actor.organization_id, [u.id for u, _ in rows], today)
    items = []
    for user, joined_at in rows:
        student_mobilities = mobilities.get(user.id, [])
        if zone and not any(COUNTRY_ZONES.get(m.country_code) == zone for m in student_mobilities):
            continue
        if advisor_id and not any(
            m.advisor and m.advisor.member_id == advisor_id for m in student_mobilities
        ):
            continue
        if unassigned and not any(m.advisor is None for m in student_mobilities):
            continue
        current = _current(student_mobilities, actor)
        state = follow_up(current, actor.organization.settings, today)
        if status and state != status:
            continue
        items.append(
            StudentListItem(
                id=user.id,
                name=user.name,
                email=user.email,
                joined_at=joined_at,
                follow_up=state,
                mobility=current,
            )
        )
    start = (page - 1) * per_page
    return items[start : start + per_page], len(items)


async def _ensure_visible(db: AsyncSession, actor: Actor, student_id: uuid.UUID) -> None:
    if not await can_view_student(db, actor, student_id):
        raise NotFoundError("Student not found")


async def get_student(
    db: AsyncSession, actor: Actor, student_id: uuid.UUID, today: date | None = None
) -> StudentDetail:
    today = today or date.today()
    await _ensure_visible(db, actor, student_id)
    user, enrollment = (
        await db.execute(
            select(User, StudentEnrollment)
            .join(StudentEnrollment, StudentEnrollment.student_id == User.id)
            .where(
                User.id == student_id,
                StudentEnrollment.organization_id == actor.organization_id,
                StudentEnrollment.status == EnrollmentStatus.ACTIVE,
            )
        )
    ).one()

    mobilities = (
        await _mobilities(db, actor.organization_id, [user.id], today, include_completed=True)
    ).get(user.id, [])
    mobility_ids = [m.id for m in mobilities]
    categories: dict[uuid.UUID, list[CategoryProgress]] = {}
    documents: dict[uuid.UUID, list[DocumentStatus]] = {}
    if mobility_ids:
        rows = await db.execute(
            select(
                Task.mobility_id,
                Task.category,
                func.count(Task.id),
                func.sum(case((Task.is_completed, 1), else_=0)).cast(Integer),
            )
            .where(Task.mobility_id.in_(mobility_ids))
            .group_by(Task.mobility_id, Task.category)
            .order_by(Task.category)
        )
        for mobility_id, category, total, done in rows.all():
            categories.setdefault(mobility_id, []).append(
                CategoryProgress(category=category, done=done or 0, total=total)
            )
        rows = await db.execute(
            select(Document.id, Document.mobility_id, Document.category, Document.uploaded_at)
            .where(Document.mobility_id.in_(mobility_ids))
            .order_by(Document.uploaded_at)
        )
        for document_id, mobility_id, category, uploaded_at in rows.all():
            documents.setdefault(mobility_id, []).append(
                DocumentStatus(id=document_id, category=category, uploaded_at=uploaded_at)
            )

    return StudentDetail(
        id=user.id,
        name=user.name,
        email=user.email,
        phone=user.phone,
        joined_at=enrollment.joined_at,
        source=enrollment.source,
        follow_up=follow_up(_current(mobilities, actor), actor.organization.settings, today),
        mobilities=[
            StudentMobilityDetail(
                **m.model_dump(),
                categories=categories.get(m.id, []),
                documents=documents.get(m.id, []),
            )
            for m in mobilities
        ],
    )


async def list_notes(db: AsyncSession, actor: Actor, student_id: uuid.UUID) -> list[NoteRead]:
    await _ensure_visible(db, actor, student_id)
    notes = list(
        await db.scalars(
            select(StudentNote)
            .where(
                StudentNote.organization_id == actor.organization_id,
                StudentNote.student_id == student_id,
            )
            .order_by(StudentNote.created_at.desc())
        )
    )
    names = await _advisor_names(db, {n.author_member_id for n in notes if n.author_member_id})
    return [
        NoteRead(
            id=note.id,
            body=note.body,
            author=AdvisorRef(member_id=note.author_member_id, name=names[note.author_member_id])
            if note.author_member_id
            else None,
            created_at=note.created_at,
        )
        for note in notes
    ]


async def add_note(db: AsyncSession, actor: Actor, student_id: uuid.UUID, body: str) -> NoteRead:
    await _ensure_visible(db, actor, student_id)
    note = StudentNote(
        organization_id=actor.organization_id,
        student_id=student_id,
        author_member_id=actor.membership.id,
        body=body,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return NoteRead(
        id=note.id,
        body=note.body,
        author=AdvisorRef(member_id=actor.membership.id, name=actor.user.name),
        created_at=note.created_at,
    )
