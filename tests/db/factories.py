import uuid
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from src.app.core.security import create_access_token, hash_password
from src.app.models.contract import Contract
from src.app.models.destination import Destination
from src.app.models.enums import (
    AccountType,
    ContractStatus,
    EnrollmentSource,
    EnrollmentStatus,
    OrganizationStatus,
    OrgRole,
)
from src.app.models.mobility import Mobility
from src.app.models.organization import Organization
from src.app.models.organization_member import OrganizationMember
from src.app.models.student_enrollment import StudentEnrollment
from src.app.models.user import User
from src.app.services.organization_service import generate_join_code

PASSWORD = "password123"
_PASSWORD_HASH = hash_password(PASSWORD)


def _suffix() -> str:
    return uuid.uuid4().hex[:8]


async def make_user(
    db: AsyncSession, account_type: AccountType = AccountType.STUDENT, **fields
) -> User:
    user = User(
        email=fields.pop("email", f"user-{_suffix()}@example.com"),
        name=fields.pop("name", "Test User"),
        password_hash=_PASSWORD_HASH,
        account_type=account_type,
        **fields,
    )
    db.add(user)
    await db.flush()
    return user


async def make_organization(db: AsyncSession, **fields) -> Organization:
    suffix = _suffix()
    organization = Organization(
        name=fields.pop("name", f"School {suffix}"),
        slug=fields.pop("slug", f"school-{suffix}"),
        join_code=fields.pop("join_code", None) or generate_join_code(),
        status=fields.pop("status", OrganizationStatus.ACTIVE),
        **fields,
    )
    db.add(organization)
    await db.flush()
    return organization


async def make_member(
    db: AsyncSession,
    organization: Organization,
    org_role: OrgRole = OrgRole.ADVISOR,
    user: User | None = None,
    is_active: bool = True,
) -> OrganizationMember:
    user = user or await make_user(db, AccountType.ORG_STAFF)
    member = OrganizationMember(
        organization_id=organization.id, user_id=user.id, org_role=org_role, is_active=is_active
    )
    db.add(member)
    await db.flush()
    return member


async def make_enrollment(
    db: AsyncSession,
    organization: Organization,
    student: User,
    status: EnrollmentStatus = EnrollmentStatus.ACTIVE,
) -> StudentEnrollment:
    enrollment = StudentEnrollment(
        organization_id=organization.id,
        student_id=student.id,
        status=status,
        source=EnrollmentSource.JOIN_CODE,
    )
    db.add(enrollment)
    await db.flush()
    return enrollment


async def make_destination(db: AsyncSession, **fields) -> Destination:
    destination = Destination(
        country=fields.pop("country", "Espagne"),
        country_code=fields.pop("country_code", "ES"),
        city=fields.pop("city", f"City {_suffix()}"),
        **fields,
    )
    db.add(destination)
    await db.flush()
    return destination


async def make_mobility(db: AsyncSession, student: User, destination: Destination) -> Mobility:
    mobility = Mobility(
        user_id=student.id,
        destination_id=destination.id,
        type="erasmus",
        departure_date=date.today() + timedelta(days=90),
        status="preparing",
    )
    db.add(mobility)
    await db.flush()
    return mobility


def auth_headers(user: User, session_id: str | None = None, mfa: bool = False) -> dict[str, str]:
    token = create_access_token(
        user.id,
        session_id=session_id,
        token_version=user.token_version,
        account_type=user.account_type.value,
        mfa=mfa,
    )
    return {"Authorization": f"Bearer {token}"}


async def make_platform_admin(db: AsyncSession, **fields) -> User:
    return await make_user(db, AccountType.PLATFORM_ADMIN, mfa_enabled=True, **fields)


async def make_contract(
    db: AsyncSession,
    organization: Organization,
    status: ContractStatus = ContractStatus.ACTIVE,
    start: date | None = None,
    end: date | None = None,
    **fields,
) -> Contract:
    contract = Contract(
        organization_id=organization.id,
        plan=fields.pop("plan", "standard"),
        status=status,
        start_date=start or date.today() - timedelta(days=30),
        end_date=end or date.today() + timedelta(days=335),
        price_cents=fields.pop("price_cents", 0 if status == ContractStatus.PILOT else 100_000),
        **fields,
    )
    db.add(contract)
    await db.flush()
    return contract
