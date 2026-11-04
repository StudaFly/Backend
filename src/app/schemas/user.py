import uuid
from datetime import datetime

from pydantic import EmailStr, field_validator, model_validator

from src.app.schemas.common import StudaFlyBaseModel


class UserCreate(StudaFlyBaseModel):
    email: EmailStr
    password: str
    name: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserLogin(StudaFlyBaseModel):
    email: EmailStr
    password: str


class UserRead(StudaFlyBaseModel):
    id: uuid.UUID
    email: str
    name: str
    role: str
    institution_id: uuid.UUID | None = None
    is_premium: bool
    email_verified: bool
    oauth_provider: str | None
    avatar_emoji: str | None
    phone: str | None
    enable_notifications: bool
    created_at: datetime


class UserUpdate(StudaFlyBaseModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    institution: str | None = None
    enable_notifications: bool | None = None
    avatar_emoji: str | None = None
    profile_picture_uri: str | None = None


class AuthResponse(StudaFlyBaseModel):
    user: UserRead
    access_token: str
    refresh_token: str
    # True when the account was just created (OAuth sign-up): clients run the onboarding.
    is_new_user: bool = False


class GoogleAuthRequest(StudaFlyBaseModel):
    """Either an ID token (mobile, native sign-in) or an authorization code (web popup)."""

    id_token: str | None = None
    code: str | None = None

    @model_validator(mode="after")
    def exactly_one_credential(self) -> "GoogleAuthRequest":
        if bool(self.id_token) == bool(self.code):
            raise ValueError("Provide either idToken or code")
        return self


class RefreshRequest(StudaFlyBaseModel):
    refresh_token: str


class VerifyEmailRequest(StudaFlyBaseModel):
    token: str
