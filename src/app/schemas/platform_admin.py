import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import EmailStr, Field, model_validator

from src.app.models.enums import (
    AccountType,
    ContractStatus,
    EnrollmentSource,
    EnrollmentStatus,
    OrganizationStatus,
    OrgRole,
    PremiumSource,
    UserStatus,
)
from src.app.schemas.common import StrictInput, StudaFlyBaseModel
from src.app.schemas.organization import OrganizationSummary
from src.app.schemas.user import PremiumRead


class ManagedUserRead(StudaFlyBaseModel):
    id: uuid.UUID
    email: str
    name: str
    account_type: AccountType
    status: UserStatus
    org_role: OrgRole | None = None
    organization: OrganizationSummary | None = None
    premium: PremiumRead
    mfa_enabled: bool
    last_login_at: datetime | None = None
    created_at: datetime


class PremiumGrantRead(StudaFlyBaseModel):
    id: uuid.UUID
    source: PremiumSource
    starts_at: datetime
    ends_at: datetime | None = None
    revoked_at: datetime | None = None
    reason: str | None = None
    amount_cents: int | None = None
    currency: str | None = None
    created_at: datetime


class ManagedMobility(StudaFlyBaseModel):
    id: uuid.UUID
    type: str
    status: str
    departure_date: date
    return_date: date | None = None
    city: str
    country: str


class ManagedUserDetail(ManagedUserRead):
    phone: str | None = None
    suspended_at: datetime | None = None
    suspended_reason: str | None = None
    deletion_scheduled_at: datetime | None = None
    mobilities: list[ManagedMobility] = []
    premium_grants: list[PremiumGrantRead] = []


class ManagedUserCreate(StrictInput):
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)
    account_type: Literal[AccountType.STUDENT, AccountType.ORG_STAFF]
    organization_id: uuid.UUID | None = None
    org_role: OrgRole | None = None

    @model_validator(mode="after")
    def check_organization(self) -> "ManagedUserCreate":
        if self.account_type == AccountType.ORG_STAFF and (
            self.organization_id is None or self.org_role is None
        ):
            raise ValueError("A staff account needs organizationId and orgRole")
        if self.account_type == AccountType.STUDENT and self.org_role is not None:
            raise ValueError("A student account has no orgRole")
        return self


class ManagedUserUpdate(StrictInput):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)


class ReasonRequest(StrictInput):
    reason: str = Field(min_length=3, max_length=1000)


class StaffAccountCreate(StrictInput):
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)


class OrganizationAdminRead(StudaFlyBaseModel):
    id: uuid.UUID
    name: str
    slug: str
    logo_url: str | None = None
    branding: dict
    settings: dict
    status: OrganizationStatus
    join_code: str
    member_count: int = 0
    active_student_count: int = 0
    created_at: datetime
    updated_at: datetime


class OrganizationCreate(StrictInput):
    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=100)
    logo_url: str | None = Field(default=None, max_length=500)
    branding: dict = {}
    settings: dict = {}
    manager: StaffAccountCreate


class OrganizationUpdate(StrictInput):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=100)
    logo_url: str | None = Field(default=None, max_length=500)
    branding: dict | None = None
    settings: dict | None = None


class MemberRead(StudaFlyBaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    name: str
    org_role: OrgRole
    is_active: bool
    user_status: UserStatus
    created_at: datetime


class MemberCreate(StaffAccountCreate):
    org_role: OrgRole


class MemberUpdate(StrictInput):
    org_role: OrgRole | None = None
    is_active: bool | None = None


class EnrollmentRead(StudaFlyBaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    email: str
    name: str
    status: EnrollmentStatus
    source: EnrollmentSource
    joined_at: datetime
    ended_at: datetime | None = None


class EnrollmentCreate(StrictInput):
    student_id: uuid.UUID


class ArchiveResult(StudaFlyBaseModel):
    organization: OrganizationAdminRead
    deactivated_members: list[MemberRead]


class AuditLogRead(StudaFlyBaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None = None
    actor_account_type: str
    action: str
    target_type: str
    target_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    changes: dict
    ip: str | None = None
    user_agent: str | None = None
    created_at: datetime


class CountsByStatus(StudaFlyBaseModel):
    total: int
    by_status: dict[str, int]


class UserCounts(CountsByStatus):
    by_account_type: dict[str, int]


class PremiumCounts(StudaFlyBaseModel):
    purchase: int
    admin_grant: int


class PlatformOverview(StudaFlyBaseModel):
    users: UserCounts
    organizations: CountsByStatus
    contracts: CountsByStatus
    active_premium_grants: PremiumCounts


class PremiumGrantCreate(StrictInput):
    ends_at: datetime | None = None
    reason: str = Field(min_length=3, max_length=1000)


class PurchaseRead(PremiumGrantRead):
    user_id: uuid.UUID
    email: str
    stripe_payment_ref: str | None = None


class ContractRead(StudaFlyBaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    plan: str
    status: ContractStatus
    start_date: date
    end_date: date
    price_cents: int
    currency: str
    student_quota: int | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class ContractCreate(StrictInput):
    plan: str = Field(min_length=1, max_length=50)
    status: ContractStatus
    start_date: date
    end_date: date
    price_cents: int = Field(default=0, ge=0)
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    student_quota: int | None = Field(default=None, ge=1)
    notes: str | None = Field(default=None, max_length=5000)


class ContractUpdate(StrictInput):
    plan: str | None = Field(default=None, min_length=1, max_length=50)
    status: ContractStatus | None = None
    start_date: date | None = None
    end_date: date | None = None
    price_cents: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    student_quota: int | None = Field(default=None, ge=1)
    notes: str | None = Field(default=None, max_length=5000)
