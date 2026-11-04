from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.authz import Actor, require_account_type
from src.app.core.dependencies import get_current_user
from src.app.db.session import get_db
from src.app.models.enums import AccountType
from src.app.models.user import User
from src.app.schemas.common import ResponseBase
from src.app.schemas.user import UserRead, UserUpdate
from src.app.services import account_service, export_service, organization_service, user_service
from src.app.services.audit_service import RequestMeta, get_request_meta

router = APIRouter()


@router.get("/me", response_model=ResponseBase[UserRead])
async def get_me(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResponseBase[UserRead]:
    user = await user_service.get_by_id(db, current_user.id)
    return ResponseBase(data=user, message="OK")


@router.patch("/me", response_model=ResponseBase[UserRead])
async def update_me(
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResponseBase[UserRead]:
    user = await user_service.update(db, current_user.id, payload)
    return ResponseBase(data=user, message="Profile updated successfully")


@router.delete("/me", status_code=204)
async def delete_me(
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    await account_service.request_own_deletion(db, current_user, meta)
    return Response(status_code=204)


@router.get("/me/export")
async def export_me(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONResponse:
    data = await export_service.export_user(db, current_user)
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": 'attachment; filename="studafly-export.json"'},
    )


@router.delete("/me/organization", status_code=204)
async def leave_organization(
    actor: Actor = Depends(require_account_type(AccountType.STUDENT)),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await organization_service.leave_organization(db, actor.user, meta)
    return Response(status_code=204)
