from datetime import datetime

from pydantic import Field

from src.app.models.enums import InvitationKind, InvitationStatus, OrgRole
from src.app.schemas.common import StrictInput, StudaFlyBaseModel
from src.app.schemas.organization import OrganizationSummary
from src.app.schemas.user import AuthResponse

SHARED_WITH_SCHOOL = [
    "profile",
    "mobilities",
    "tasks",
    "progress",
    "document_status",
    "staff_notes",
]
NEVER_SHARED = ["document_content"]


class InvitationPreview(StudaFlyBaseModel):
    organization: OrganizationSummary
    kind: InvitationKind
    org_role: OrgRole | None = None
    email: str
    status: InvitationStatus
    expires_at: datetime
    shared_with_school: list[str] = SHARED_WITH_SCHOOL
    never_shared: list[str] = NEVER_SHARED


class InvitationAccept(StrictInput):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    password: str | None = Field(default=None, min_length=8)


class InvitationAcceptResult(StudaFlyBaseModel):
    kind: InvitationKind
    organization: OrganizationSummary
    auth: AuthResponse | None = None


class JoinRequest(StrictInput):
    code: str = Field(min_length=4, max_length=32)


class OrganizationPreview(StudaFlyBaseModel):
    organization: OrganizationSummary
    shared_with_school: list[str] = SHARED_WITH_SCHOOL
    never_shared: list[str] = NEVER_SHARED
