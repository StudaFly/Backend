from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.authz import Actor, require_account_type
from src.app.core.dependencies import get_access_payload, get_current_user
from src.app.db.session import get_db
from src.app.models.enums import AccountType
from src.app.models.user import User
from src.app.schemas.common import ResponseBase
from src.app.schemas.user import (
    AuthResponse,
    ForgotPasswordRequest,
    MfaActivationResponse,
    MfaCodeRequest,
    MfaSetupRead,
    RefreshRequest,
    ResetPasswordRequest,
    UserCreate,
    UserLogin,
    VerifyEmailRequest,
)
from src.app.services import auth_service, mfa_service
from src.app.services.audit_service import RequestMeta, get_request_meta

router = APIRouter()


@router.post("/register", response_model=ResponseBase[AuthResponse], status_code=201)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    auth = await auth_service.register(db, payload)
    return ResponseBase(
        data=auth,
        message="Account created. Check your logs for the email verification token.",
    )


@router.post("/login", response_model=ResponseBase[AuthResponse])
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    auth = await auth_service.login(db, payload)
    return ResponseBase(data=auth, message="Login successful")


@router.post("/verify-email")
async def verify_email(payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    await auth_service.verify_email(db, payload.token)
    return {"data": None, "message": "Email verified successfully"}


@router.post("/refresh", response_model=ResponseBase[AuthResponse])
async def refresh_token(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    auth = await auth_service.refresh_tokens(db, payload.refresh_token)
    return ResponseBase(data=auth, message="Tokens refreshed")


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
    token: dict = Depends(get_access_payload),
):
    await auth_service.logout(current_user.id, token.get("sid"))
    return {"data": None, "message": "Logged out successfully"}


@router.post("/oauth/google")
async def oauth_google():
    # TODO: implement via auth_service.oauth_login("google", code)
    raise NotImplementedError


@router.post("/oauth/microsoft")
async def oauth_microsoft():
    # TODO: implement via auth_service.oauth_login("microsoft", code)
    raise NotImplementedError


@router.post("/oauth/apple")
async def oauth_apple():
    # TODO: implement via auth_service.oauth_login("apple", code)
    raise NotImplementedError


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    await auth_service.forgot_password(db, payload.email)
    return {"data": None, "message": "If this account exists, a reset link has been sent"}


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    await auth_service.reset_password(db, payload.token, payload.new_password)
    return {"data": None, "message": "Password updated, you can sign in"}


platform_admin_only = require_account_type(AccountType.PLATFORM_ADMIN)


@router.post("/mfa/setup", response_model=ResponseBase[MfaSetupRead])
async def mfa_setup(
    actor: Actor = Depends(platform_admin_only),
    db: AsyncSession = Depends(get_db),
):
    secret, uri = await mfa_service.start_setup(db, actor.user)
    return ResponseBase(data=MfaSetupRead(secret=secret, otpauth_uri=uri))


@router.post("/mfa/activate", response_model=ResponseBase[MfaActivationResponse])
async def mfa_activate(
    payload: MfaCodeRequest,
    actor: Actor = Depends(platform_admin_only),
    token: dict = Depends(get_access_payload),
    meta: RequestMeta = Depends(get_request_meta),
    db: AsyncSession = Depends(get_db),
):
    backup_codes = await mfa_service.activate(db, actor.user, payload.code, meta)
    auth = await auth_service.issue_tokens(db, actor.user, session_id=token.get("sid"), mfa=True)
    return ResponseBase(
        data=MfaActivationResponse(**auth.model_dump(), backup_codes=backup_codes),
        message="Multi-factor authentication enabled. Keep the backup codes somewhere safe.",
    )


@router.post("/mfa/verify", response_model=ResponseBase[AuthResponse])
async def mfa_verify(
    payload: MfaCodeRequest,
    actor: Actor = Depends(platform_admin_only),
    token: dict = Depends(get_access_payload),
    db: AsyncSession = Depends(get_db),
):
    await mfa_service.verify(db, actor.user, payload.code)
    auth = await auth_service.issue_tokens(db, actor.user, session_id=token.get("sid"), mfa=True)
    return ResponseBase(data=auth, message="Multi-factor authentication verified")
