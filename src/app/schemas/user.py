import uuid
from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from src.app.models.enums import AccountType, OrgRole
from src.app.schemas.common import StudaFlyBaseModel
from src.app.schemas.organization import OrganizationSummary


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
    account_type: AccountType
    org_role: OrgRole | None = None
    organization: OrganizationSummary | None = None
    role: str = Field(description="Deprecated: use accountType and orgRole.")
    institution_id: uuid.UUID | None = Field(
        default=None, description="Deprecated: use organization.id."
    )
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


class RefreshRequest(StudaFlyBaseModel):
    refresh_token: str


class VerifyEmailRequest(StudaFlyBaseModel):
    token: str
