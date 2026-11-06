from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.authz import Actor, require_platform_admin
from src.app.db.session import get_db
from src.app.models.enums import (
    AccountType,
    ContractStatus,
    EnrollmentSource,
    EnrollmentStatus,
    OrganizationStatus,
    UserStatus,
)
from src.app.schemas.common import PaginatedResponse, ResponseBase
from src.app.schemas.platform_admin import (
    ArchiveResult,
    AuditLogRead,
    ContractCreate,
    ContractRead,
    ContractUpdate,
    EnrollmentCreate,
    EnrollmentRead,
    ManagedUserCreate,
    ManagedUserDetail,
    ManagedUserRead,
    ManagedUserUpdate,
    MemberCreate,
    MemberRead,
    MemberUpdate,
    OrganizationAdminRead,
    OrganizationCreate,
    OrganizationUpdate,
    PlatformOverview,
    PremiumGrantCreate,
    PremiumGrantRead,
    PurchaseRead,
    ReasonRequest,
)
from src.app.services import (
    audit_service,
    contract_service,
    organization_service,
    platform_admin_service,
    premium_service,
)
from src.app.services.audit_service import RequestMeta, get_request_meta

router = APIRouter(dependencies=[Depends(require_platform_admin)])


def _page(page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100, alias="perPage")):
    return page, per_page


@router.get("/overview", response_model=ResponseBase[PlatformOverview])
async def get_overview(db: AsyncSession = Depends(get_db)):
    return ResponseBase(data=await platform_admin_service.overview(db))


@router.get("/users", response_model=PaginatedResponse[ManagedUserRead])
async def list_users(
    pagination: tuple[int, int] = Depends(_page),
    q: str | None = Query(None, max_length=100),
    account_type: AccountType | None = Query(None, alias="accountType"),
    status: UserStatus | None = None,
    organization_id: UUID | None = Query(None, alias="organizationId"),
    db: AsyncSession = Depends(get_db),
):
    page, per_page = pagination
    users, total = await platform_admin_service.list_users(
        db,
        page=page,
        per_page=per_page,
        q=q,
        account_type=account_type,
        status=status,
        organization_id=organization_id,
    )
    return PaginatedResponse(data=users, total=total, page=page, per_page=per_page)


@router.post("/users", response_model=ResponseBase[ManagedUserDetail], status_code=201)
async def create_user(
    payload: ManagedUserCreate,
    actor: Actor = Depends(require_platform_admin),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    user = await platform_admin_service.create_user(db, actor.user, payload, meta)
    return ResponseBase(data=user, message="Account created, a password setup link was sent")


@router.get("/users/{user_id}", response_model=ResponseBase[ManagedUserDetail])
async def get_user(user_id: UUID, db: AsyncSession = Depends(get_db)):
    return ResponseBase(data=await platform_admin_service.get_user_detail(db, user_id))


@router.patch("/users/{user_id}", response_model=ResponseBase[ManagedUserDetail])
async def update_user(
    user_id: UUID,
    payload: ManagedUserUpdate,
    actor: Actor = Depends(require_platform_admin),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    user = await platform_admin_service.update_user(db, actor.user, user_id, payload, meta)
    return ResponseBase(data=user)


@router.post("/users/{user_id}/suspend", response_model=ResponseBase[ManagedUserDetail])
async def suspend_user(
    user_id: UUID,
    payload: ReasonRequest,
    actor: Actor = Depends(require_platform_admin),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    user = await platform_admin_service.suspend_user(db, actor.user, user_id, payload.reason, meta)
    return ResponseBase(data=user, message="Account suspended")


@router.post("/users/{user_id}/reactivate", response_model=ResponseBase[ManagedUserDetail])
async def reactivate_user(
    user_id: UUID,
    actor: Actor = Depends(require_platform_admin),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    user = await platform_admin_service.reactivate_user(db, actor.user, user_id, meta)
    return ResponseBase(data=user, message="Account reactivated")


@router.delete("/users/{user_id}", response_model=ResponseBase[ManagedUserDetail])
async def schedule_user_deletion(
    user_id: UUID,
    actor: Actor = Depends(require_platform_admin),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    user = await platform_admin_service.schedule_deletion(db, actor.user, user_id, meta)
    return ResponseBase(data=user, message="Account scheduled for deletion")


@router.post(
    "/users/{user_id}/premium-grants",
    response_model=ResponseBase[PremiumGrantRead],
    status_code=201,
)
async def grant_premium(
    user_id: UUID,
    payload: PremiumGrantCreate,
    actor: Actor = Depends(require_platform_admin),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    grant = await platform_admin_service.grant_premium(db, actor.user, user_id, payload, meta)
    return ResponseBase(data=grant, message="Premium granted")


@router.delete(
    "/users/{user_id}/premium-grants/{grant_id}", response_model=ResponseBase[PremiumGrantRead]
)
async def revoke_premium(
    user_id: UUID,
    grant_id: UUID,
    reason: str = Query(..., min_length=3, max_length=1000),
    actor: Actor = Depends(require_platform_admin),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    grant = await platform_admin_service.revoke_premium(
        db, actor.user, user_id, grant_id, reason, meta
    )
    return ResponseBase(data=grant, message="Premium revoked")


@router.get("/purchases", response_model=PaginatedResponse[PurchaseRead])
async def list_purchases(
    pagination: tuple[int, int] = Depends(_page), db: AsyncSession = Depends(get_db)
):
    page, per_page = pagination
    purchases, total = await premium_service.list_purchases(db, page=page, per_page=per_page)
    return PaginatedResponse(data=purchases, total=total, page=page, per_page=per_page)


@router.get("/contracts", response_model=PaginatedResponse[ContractRead])
async def list_contracts(
    pagination: tuple[int, int] = Depends(_page),
    status: ContractStatus | None = None,
    organization_id: UUID | None = Query(None, alias="organizationId"),
    expiring_within: int | None = Query(None, alias="expiringWithin", ge=0, le=3650),
    db: AsyncSession = Depends(get_db),
):
    page, per_page = pagination
    contracts, total = await contract_service.list_contracts(
        db,
        page=page,
        per_page=per_page,
        organization_id=organization_id,
        status=status,
        expiring_within=expiring_within,
    )
    return PaginatedResponse(data=contracts, total=total, page=page, per_page=per_page)


@router.get(
    "/organizations/{organization_id}/contracts",
    response_model=ResponseBase[list[ContractRead]],
)
async def list_organization_contracts(organization_id: UUID, db: AsyncSession = Depends(get_db)):
    await organization_service.get_organization(db, organization_id)
    contracts, _ = await contract_service.list_contracts(
        db, page=1, per_page=1000, organization_id=organization_id
    )
    return ResponseBase(data=contracts)


@router.post(
    "/organizations/{organization_id}/contracts",
    response_model=ResponseBase[ContractRead],
    status_code=201,
)
async def create_contract(
    organization_id: UUID,
    payload: ContractCreate,
    actor: Actor = Depends(require_platform_admin),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    contract = await contract_service.create_contract(
        db, actor.user, organization_id, payload, meta
    )
    return ResponseBase(data=contract, message="Contract created")


@router.patch(
    "/organizations/{organization_id}/contracts/{contract_id}",
    response_model=ResponseBase[ContractRead],
)
async def update_contract(
    organization_id: UUID,
    contract_id: UUID,
    payload: ContractUpdate,
    actor: Actor = Depends(require_platform_admin),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    contract = await contract_service.update_contract(
        db, actor.user, organization_id, contract_id, payload, meta
    )
    return ResponseBase(data=contract)


@router.get("/organizations", response_model=PaginatedResponse[OrganizationAdminRead])
async def list_organizations(
    pagination: tuple[int, int] = Depends(_page),
    q: str | None = Query(None, max_length=100),
    status: OrganizationStatus | None = None,
    db: AsyncSession = Depends(get_db),
):
    page, per_page = pagination
    organizations, total = await organization_service.list_organizations(
        db, page=page, per_page=per_page, q=q, status=status
    )
    return PaginatedResponse(data=organizations, total=total, page=page, per_page=per_page)


@router.post("/organizations", response_model=ResponseBase[OrganizationAdminRead], status_code=201)
async def create_organization(
    payload: OrganizationCreate,
    actor: Actor = Depends(require_platform_admin),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    organization = await organization_service.create_organization(db, actor.user, payload, meta)
    return ResponseBase(data=organization, message="Organization created")


@router.get("/organizations/{organization_id}", response_model=ResponseBase[OrganizationAdminRead])
async def get_organization(organization_id: UUID, db: AsyncSession = Depends(get_db)):
    return ResponseBase(data=await organization_service.read_organization(db, organization_id))


@router.patch(
    "/organizations/{organization_id}", response_model=ResponseBase[OrganizationAdminRead]
)
async def update_organization(
    organization_id: UUID,
    payload: OrganizationUpdate,
    actor: Actor = Depends(require_platform_admin),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    organization = await organization_service.update_organization(
        db, actor.user, organization_id, payload, meta
    )
    return ResponseBase(data=organization)


@router.post(
    "/organizations/{organization_id}/suspend",
    response_model=ResponseBase[OrganizationAdminRead],
)
async def suspend_organization(
    organization_id: UUID,
    actor: Actor = Depends(require_platform_admin),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    organization = await organization_service.set_status(
        db, actor.user, organization_id, OrganizationStatus.SUSPENDED, meta
    )
    return ResponseBase(data=organization, message="Organization suspended")


@router.post(
    "/organizations/{organization_id}/reactivate",
    response_model=ResponseBase[OrganizationAdminRead],
)
async def reactivate_organization(
    organization_id: UUID,
    actor: Actor = Depends(require_platform_admin),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    organization = await organization_service.set_status(
        db, actor.user, organization_id, OrganizationStatus.ACTIVE, meta
    )
    return ResponseBase(data=organization, message="Organization reactivated")


@router.post("/organizations/{organization_id}/archive", response_model=ResponseBase[ArchiveResult])
async def archive_organization(
    organization_id: UUID,
    actor: Actor = Depends(require_platform_admin),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    result = await organization_service.archive_organization(db, actor.user, organization_id, meta)
    return ResponseBase(
        data=result,
        message="Organization archived: enrollments revoked, staff deactivated",
    )


@router.get(
    "/organizations/{organization_id}/members", response_model=ResponseBase[list[MemberRead]]
)
async def list_members(organization_id: UUID, db: AsyncSession = Depends(get_db)):
    return ResponseBase(data=await organization_service.list_members(db, organization_id))


@router.post(
    "/organizations/{organization_id}/members",
    response_model=ResponseBase[MemberRead],
    status_code=201,
)
async def add_member(
    organization_id: UUID,
    payload: MemberCreate,
    actor: Actor = Depends(require_platform_admin),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    member = await organization_service.add_member(db, actor.user, organization_id, payload, meta)
    return ResponseBase(data=member, message="Member added")


@router.patch(
    "/organizations/{organization_id}/members/{member_id}",
    response_model=ResponseBase[MemberRead],
)
async def update_member(
    organization_id: UUID,
    member_id: UUID,
    payload: MemberUpdate,
    actor: Actor = Depends(require_platform_admin),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    member = await organization_service.update_member(
        db, actor.user, organization_id, member_id, payload, meta
    )
    return ResponseBase(data=member)


@router.delete("/organizations/{organization_id}/members/{member_id}", status_code=204)
async def remove_member(
    organization_id: UUID,
    member_id: UUID,
    actor: Actor = Depends(require_platform_admin),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    await organization_service.remove_member(db, actor.user, organization_id, member_id, meta)
    return Response(status_code=204)


@router.get(
    "/organizations/{organization_id}/students",
    response_model=ResponseBase[list[EnrollmentRead]],
)
async def list_students(
    organization_id: UUID,
    status: EnrollmentStatus | None = EnrollmentStatus.ACTIVE,
    db: AsyncSession = Depends(get_db),
):
    enrollments = await organization_service.list_enrollments(db, organization_id, status)
    return ResponseBase(data=enrollments)


@router.post(
    "/organizations/{organization_id}/students",
    response_model=ResponseBase[EnrollmentRead],
    status_code=201,
)
async def enroll_student(
    organization_id: UUID,
    payload: EnrollmentCreate,
    actor: Actor = Depends(require_platform_admin),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    enrollment = await organization_service.enroll_student(
        db, actor.user, organization_id, payload.student_id, EnrollmentSource.ADMIN, meta
    )
    return ResponseBase(data=enrollment, message="Student enrolled")


@router.delete("/organizations/{organization_id}/students/{student_id}", status_code=204)
async def revoke_enrollment(
    organization_id: UUID,
    student_id: UUID,
    actor: Actor = Depends(require_platform_admin),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    await organization_service.revoke_enrollment(db, actor.user, organization_id, student_id, meta)
    return Response(status_code=204)


@router.get("/audit-logs", response_model=PaginatedResponse[AuditLogRead])
async def list_audit_logs(
    pagination: tuple[int, int] = Depends(_page),
    actor_id: UUID | None = Query(None, alias="actorId"),
    target_type: str | None = Query(None, alias="targetType", max_length=50),
    target_id: UUID | None = Query(None, alias="targetId"),
    organization_id: UUID | None = Query(None, alias="organizationId"),
    action: str | None = Query(None, max_length=100),
    since: datetime | None = None,
    until: datetime | None = None,
    db: AsyncSession = Depends(get_db),
):
    page, per_page = pagination
    entries, total = await audit_service.list_entries(
        db,
        page=page,
        per_page=per_page,
        actor_id=actor_id,
        target_type=target_type,
        target_id=target_id,
        organization_id=organization_id,
        action=action,
        since=since,
        until=until,
    )
    return PaginatedResponse(
        data=[AuditLogRead.model_validate(e) for e in entries],
        total=total,
        page=page,
        per_page=per_page,
    )
