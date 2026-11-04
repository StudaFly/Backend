from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.dependencies import get_optional_user
from src.app.db.session import get_db
from src.app.models.user import User
from src.app.schemas.common import ResponseBase
from src.app.schemas.invitation import (
    InvitationAccept,
    InvitationAcceptResult,
    InvitationPreview,
)
from src.app.services import invitation_service
from src.app.services.audit_service import RequestMeta, get_request_meta

router = APIRouter()


@router.get("/{token}", response_model=ResponseBase[InvitationPreview])
async def preview_invitation(token: str, db: AsyncSession = Depends(get_db)):
    return ResponseBase(data=await invitation_service.preview(db, token))


@router.post("/{token}/accept", response_model=ResponseBase[InvitationAcceptResult])
async def accept_invitation(
    token: str,
    payload: InvitationAccept | None = None,
    current_user: User | None = Depends(get_optional_user),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    result = await invitation_service.accept(
        db, token, current_user, payload or InvitationAccept(), meta
    )
    return ResponseBase(data=result, message=f"Welcome to {result.organization.name}")
