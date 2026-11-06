from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.authz import Actor, require_org_role
from src.app.core.exceptions import ForbiddenError
from src.app.core.zones import ZONES, fully_covered_zones
from src.app.db.session import get_db
from src.app.models.enums import InvitationKind, InvitationStatus, OrgRole
from src.app.schemas.common import PaginatedResponse, ResponseBase
from src.app.schemas.org import (
    AdvisorAssignment,
    FollowUp,
    ImportReport,
    InvitationRead,
    JoinCodeRead,
    NoteCreate,
    NoteRead,
    OrgContractRead,
    OrgRead,
    OrgSettingsUpdate,
    PerimeterRead,
    PerimeterUpdate,
    StaffInvitationCreate,
    StudentDetail,
    StudentInvitationCreate,
    StudentListItem,
    ZoneRead,
)
from src.app.schemas.platform_admin import AuditLogRead, MemberRead, MemberUpdate
from src.app.services import (
    audit_service,
    contract_service,
    invitation_service,
    org_student_service,
    organization_service,
    perimeter_service,
)
from src.app.services.audit_service import RequestMeta, get_request_meta

router = APIRouter(dependencies=[Depends(require_org_role())])

any_member = require_org_role()
manager_only = require_org_role(OrgRole.MANAGER)


def _page(page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100, alias="perPage")):
    return page, per_page


async def _org_read(db: AsyncSession, actor: Actor) -> OrgRead:
    countries = await perimeter_service.member_countries(db, actor.membership.id)
    organization = actor.organization
    return OrgRead(
        id=organization.id,
        name=organization.name,
        slug=organization.slug,
        logo_url=organization.logo_url,
        branding=organization.branding,
        settings=organization.settings,
        my_member_id=actor.membership.id,
        my_org_role=actor.org_role,
        my_countries=countries,
        my_zones=fully_covered_zones(set(countries)),
    )


@router.get("", response_model=ResponseBase[OrgRead])
async def get_org(actor: Actor = Depends(any_member), db: AsyncSession = Depends(get_db)):
    return ResponseBase(data=await _org_read(db, actor))


@router.patch("", response_model=ResponseBase[OrgRead])
async def update_org(
    payload: OrgSettingsUpdate,
    actor: Actor = Depends(manager_only),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    await organization_service.update_organization(
        db, actor.user, actor.organization_id, payload, meta
    )
    await db.refresh(actor.organization)
    return ResponseBase(data=await _org_read(db, actor))


@router.get("/contract", response_model=ResponseBase[OrgContractRead])
async def get_contract(actor: Actor = Depends(manager_only), db: AsyncSession = Depends(get_db)):
    return ResponseBase(data=await contract_service.org_contract(db, actor.organization_id))


@router.get("/members", response_model=ResponseBase[list[MemberRead]])
async def list_members(actor: Actor = Depends(any_member), db: AsyncSession = Depends(get_db)):
    return ResponseBase(data=await organization_service.list_members(db, actor.organization_id))


@router.post("/members", response_model=ResponseBase[InvitationRead], status_code=201)
async def invite_staff(
    payload: StaffInvitationCreate,
    actor: Actor = Depends(manager_only),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    invitation = await invitation_service.invite_staff(
        db, actor, payload.email, payload.org_role, meta
    )
    return ResponseBase(data=invitation, message="Invitation sent")


@router.patch("/members/{member_id}", response_model=ResponseBase[MemberRead])
async def update_member(
    member_id: UUID,
    payload: MemberUpdate,
    actor: Actor = Depends(manager_only),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    member = await organization_service.update_member(
        db, actor.user, actor.organization_id, member_id, payload, meta
    )
    return ResponseBase(data=member)


@router.delete("/members/{member_id}", status_code=204)
async def remove_member(
    member_id: UUID,
    actor: Actor = Depends(manager_only),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    await organization_service.remove_member(db, actor.user, actor.organization_id, member_id, meta)
    return Response(status_code=204)


@router.get("/zones", response_model=ResponseBase[list[ZoneRead]])
async def list_zones():
    return ResponseBase(
        data=[ZoneRead(key=zone, countries=list(countries)) for zone, countries in ZONES.items()]
    )


@router.get("/members/{member_id}/perimeter", response_model=ResponseBase[PerimeterRead])
async def get_perimeter(
    member_id: UUID, actor: Actor = Depends(any_member), db: AsyncSession = Depends(get_db)
):
    if actor.org_role != OrgRole.MANAGER and member_id != actor.membership.id:
        raise ForbiddenError("An advisor can only see their own perimeter")
    perimeter = await perimeter_service.get_perimeter(db, actor.organization_id, member_id)
    return ResponseBase(data=perimeter)


@router.put("/members/{member_id}/perimeter", response_model=ResponseBase[PerimeterRead])
async def set_perimeter(
    member_id: UUID,
    payload: PerimeterUpdate,
    actor: Actor = Depends(manager_only),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    perimeter = await perimeter_service.set_perimeter(
        db, actor.user, actor.organization_id, member_id, payload, meta
    )
    return ResponseBase(data=perimeter)


@router.get("/students", response_model=PaginatedResponse[StudentListItem])
async def list_students(
    pagination: tuple[int, int] = Depends(_page),
    q: str | None = Query(None, max_length=100),
    status: FollowUp | None = None,
    zone: str | None = Query(None, max_length=50),
    advisor_id: UUID | None = Query(None, alias="advisorId"),
    unassigned: bool = False,
    actor: Actor = Depends(any_member),
    db: AsyncSession = Depends(get_db),
):
    page, per_page = pagination
    students, total = await org_student_service.list_students(
        db,
        actor,
        page=page,
        per_page=per_page,
        q=q,
        status=status,
        zone=zone,
        advisor_id=advisor_id,
        unassigned=unassigned,
        today=date.today(),
    )
    return PaginatedResponse(data=students, total=total, page=page, per_page=per_page)


@router.get("/students/{student_id}", response_model=ResponseBase[StudentDetail])
async def get_student(
    student_id: UUID, actor: Actor = Depends(any_member), db: AsyncSession = Depends(get_db)
):
    return ResponseBase(data=await org_student_service.get_student(db, actor, student_id))


@router.delete("/students/{student_id}", status_code=204)
async def revoke_student(
    student_id: UUID,
    actor: Actor = Depends(manager_only),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    await organization_service.revoke_enrollment(
        db, actor.user, actor.organization_id, student_id, meta
    )
    return Response(status_code=204)


@router.get("/students/{student_id}/notes", response_model=ResponseBase[list[NoteRead]])
async def list_notes(
    student_id: UUID, actor: Actor = Depends(any_member), db: AsyncSession = Depends(get_db)
):
    return ResponseBase(data=await org_student_service.list_notes(db, actor, student_id))


@router.post("/students/{student_id}/notes", response_model=ResponseBase[NoteRead], status_code=201)
async def add_note(
    student_id: UUID,
    payload: NoteCreate,
    actor: Actor = Depends(any_member),
    db: AsyncSession = Depends(get_db),
):
    note = await org_student_service.add_note(db, actor, student_id, payload.body)
    return ResponseBase(data=note, message="Note added")


@router.put("/mobilities/{mobility_id}/advisor", status_code=204)
async def assign_advisor(
    mobility_id: UUID,
    payload: AdvisorAssignment,
    actor: Actor = Depends(manager_only),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    await perimeter_service.set_override(
        db, actor.user, actor.organization_id, mobility_id, payload.member_id, meta
    )
    return Response(status_code=204)


@router.delete("/mobilities/{mobility_id}/advisor", status_code=204)
async def clear_advisor(
    mobility_id: UUID,
    actor: Actor = Depends(manager_only),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    await perimeter_service.clear_override(db, actor.user, actor.organization_id, mobility_id, meta)
    return Response(status_code=204)


@router.get("/invitations", response_model=ResponseBase[list[InvitationRead]])
async def list_invitations(
    status: InvitationStatus | None = None,
    kind: InvitationKind | None = None,
    actor: Actor = Depends(any_member),
    db: AsyncSession = Depends(get_db),
):
    invitations = await invitation_service.list_invitations(db, actor, status, kind)
    return ResponseBase(data=invitations)


@router.post("/invitations", response_model=ResponseBase[InvitationRead], status_code=201)
async def invite_student(
    payload: StudentInvitationCreate,
    actor: Actor = Depends(any_member),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    invitation = await invitation_service.invite_student(db, actor, payload.email, meta)
    return ResponseBase(data=invitation, message="Invitation sent")


@router.post("/invitations/import", response_model=ResponseBase[ImportReport])
async def import_invitations(
    file: UploadFile = File(...),
    actor: Actor = Depends(any_member),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read(invitation_service.MAX_CSV_BYTES + 1)
    report = await invitation_service.import_csv(db, actor, content, meta)
    return ResponseBase(data=report, message="Import finished")


@router.delete("/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(
    invitation_id: UUID,
    actor: Actor = Depends(any_member),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    await invitation_service.revoke(db, actor, invitation_id, meta)
    return Response(status_code=204)


@router.get("/join-code", response_model=ResponseBase[JoinCodeRead])
async def get_join_code(actor: Actor = Depends(any_member)):
    return ResponseBase(data=JoinCodeRead(join_code=actor.organization.join_code))


@router.post("/join-code/rotate", response_model=ResponseBase[JoinCodeRead])
async def rotate_join_code(
    actor: Actor = Depends(manager_only),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    code = await organization_service.rotate_join_code(db, actor.user, actor.organization_id, meta)
    return ResponseBase(data=JoinCodeRead(join_code=code), message="New school code generated")


@router.get("/audit-logs", response_model=PaginatedResponse[AuditLogRead])
async def list_audit_logs(
    pagination: tuple[int, int] = Depends(_page),
    action: str | None = Query(None, max_length=100),
    actor: Actor = Depends(manager_only),
    db: AsyncSession = Depends(get_db),
):
    page, per_page = pagination
    entries, total = await audit_service.list_entries(
        db, page=page, per_page=per_page, organization_id=actor.organization_id, action=action
    )
    return PaginatedResponse(
        data=[AuditLogRead.model_validate(e) for e in entries],
        total=total,
        page=page,
        per_page=per_page,
    )
