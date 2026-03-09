from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.dependencies import get_current_user
from src.app.db.session import get_db
from src.app.schemas.user import (
    RefreshRequest,
    UserCreate,
    UserLogin,
    UserRead,
    VerifyEmailRequest,
)
from src.app.services import auth_service

router = APIRouter()


@router.post("/register", status_code=201)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    user = await auth_service.register(db, payload)
    return {
        "data": UserRead.model_validate(user),
        "message": "Account created. Check your logs for the email verification token.",
    }


@router.post("/login", response_model=None)
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    tokens = await auth_service.login(db, payload)
    return {"data": tokens, "message": "Login successful"}


@router.post("/verify-email")
async def verify_email(payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    await auth_service.verify_email(db, payload.token)
    return {"data": None, "message": "Email verified successfully"}


@router.post("/refresh")
async def refresh_token(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    tokens = await auth_service.refresh_tokens(db, payload.refresh_token)
    return {"data": tokens, "message": "Tokens refreshed"}


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    await auth_service.logout(current_user["sub"])
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
async def forgot_password():
    # TODO: implement via auth_service.forgot_password()
    raise NotImplementedError


@router.post("/reset-password")
async def reset_password():
    # TODO: implement via auth_service.reset_password()
    raise NotImplementedError
