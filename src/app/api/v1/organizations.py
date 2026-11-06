from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.authz import Actor, require_account_type
from src.app.db.session import get_db
from src.app.models.enums import AccountType
from src.app.schemas.common import ResponseBase
from src.app.schemas.invitation import JoinRequest, OrganizationPreview
from src.app.schemas.organization import OrganizationSummary
from src.app.services import organization_service
from src.app.services.audit_service import RequestMeta, get_request_meta

router = APIRouter()

student_only = require_account_type(AccountType.STUDENT)


@router.get("/by-code/{code}", response_model=ResponseBase[OrganizationPreview])
async def preview_by_code(
    code: str, _: Actor = Depends(student_only), db: AsyncSession = Depends(get_db)
):
    organization = await organization_service.find_by_join_code(db, code)
    return ResponseBase(
        data=OrganizationPreview(organization=OrganizationSummary.model_validate(organization))
    )


@router.post("/join", response_model=ResponseBase[OrganizationSummary])
async def join_organization(
    payload: JoinRequest,
    actor: Actor = Depends(student_only),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    organization = await organization_service.join_by_code(db, actor.user, payload.code, meta)
    return ResponseBase(
        data=OrganizationSummary.model_validate(organization),
        message=f"You joined {organization.name}",
    )
