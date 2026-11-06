import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import EmailStr, Field, field_validator

from src.app.core.zones import COUNTRY_ZONES
from src.app.models.enums import EnrollmentSource, InvitationKind, InvitationStatus, OrgRole
from src.app.schemas.common import StrictInput, StudaFlyBaseModel
from src.app.schemas.organization import OrganizationSummary

FollowUp = Literal["ok", "warning", "danger"]
AssignmentSource = Literal["override", "perimeter"]


class OrgRead(OrganizationSummary):
    settings: dict
    my_member_id: uuid.UUID
    my_org_role: OrgRole
    my_countries: list[str]
    my_zones: list[str]


class OrgSettingsUpdate(StrictInput):
    logo_url: str | None = Field(default=None, max_length=500)
    branding: dict | None = None
    settings: dict | None = None


class ZoneRead(StudaFlyBaseModel):
    key: str
    countries: list[str]


class PerimeterRead(StudaFlyBaseModel):
    member_id: uuid.UUID
    countries: list[str]
    zones: list[str]


class PerimeterUpdate(StrictInput):
    countries: list[str] = Field(max_length=250)
    reassign: bool = False

    @field_validator("countries")
    @classmethod
    def known_countries(cls, value: list[str]) -> list[str]:
        codes = sorted({code.upper() for code in value})
        unknown = [code for code in codes if code not in COUNTRY_ZONES]
        if unknown:
            raise ValueError(f"Unknown country codes: {', '.join(unknown)}")
        return codes


class AdvisorRef(StudaFlyBaseModel):
    member_id: uuid.UUID
    name: str


class StudentMobility(StudaFlyBaseModel):
    id: uuid.UUID
    type: str
    status: str
    departure_date: date
    return_date: date | None = None
    city: str
    country: str
    country_code: str | None = None
    advisor: AdvisorRef | None = None
    assignment: AssignmentSource | None = None
    tasks_done: int = 0
    tasks_total: int = 0
    overdue_tasks: int = 0
    progress: int = 0


class StudentListItem(StudaFlyBaseModel):
    id: uuid.UUID
    name: str
    email: str
    joined_at: datetime
    follow_up: FollowUp | None = None
    mobility: StudentMobility | None = None


class CategoryProgress(StudaFlyBaseModel):
    category: str
    done: int
    total: int


class DocumentStatus(StudaFlyBaseModel):
    id: uuid.UUID
    category: str | None = None
    uploaded_at: datetime


class StudentMobilityDetail(StudentMobility):
    categories: list[CategoryProgress] = []
    documents: list[DocumentStatus] = []


class StudentDetail(StudaFlyBaseModel):
    id: uuid.UUID
    name: str
    email: str
    phone: str | None = None
    joined_at: datetime
    source: EnrollmentSource
    follow_up: FollowUp | None = None
    mobilities: list[StudentMobilityDetail]


class NoteRead(StudaFlyBaseModel):
    id: uuid.UUID
    body: str
    author: AdvisorRef | None = None
    created_at: datetime


class NoteCreate(StrictInput):
    body: str = Field(min_length=1, max_length=5000)


class AdvisorAssignment(StrictInput):
    member_id: uuid.UUID


class JoinCodeRead(StudaFlyBaseModel):
    join_code: str


class InvitationRead(StudaFlyBaseModel):
    id: uuid.UUID
    email: str
    kind: InvitationKind
    org_role: OrgRole | None = None
    status: InvitationStatus
    from_csv: bool
    expires_at: datetime
    accepted_at: datetime | None = None
    created_at: datetime


class StudentInvitationCreate(StrictInput):
    email: EmailStr


class StaffInvitationCreate(StrictInput):
    email: EmailStr
    org_role: OrgRole


ImportStatus = Literal[
    "invited", "resent", "already_member", "not_a_student", "invalid_email", "duplicate"
]


class ImportLine(StudaFlyBaseModel):
    line: int
    email: str | None = None
    status: ImportStatus


class ImportReport(StudaFlyBaseModel):
    invited: int
    resent: int
    skipped: int
    lines: list[ImportLine]


class OrgContractTerms(StudaFlyBaseModel):
    plan: str
    status: str
    start_date: date
    end_date: date
    price_cents: int
    currency: str
    student_quota: int | None = None


class OrgContractRead(StudaFlyBaseModel):
    state: Literal["none", "current", "read_only", "blocked"]
    contract: OrgContractTerms | None = None
    active_students: int
