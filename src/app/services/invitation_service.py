import csv
import hashlib
import io
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.authz.actor import Actor
from src.app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    StudaFlyException,
    UnauthorizedError,
)
from src.app.core.security import hash_password
from src.app.models.enums import (
    AccountType,
    EnrollmentSource,
    EnrollmentStatus,
    InvitationKind,
    InvitationStatus,
    OrganizationStatus,
    OrgRole,
)
from src.app.models.invitation import Invitation
from src.app.models.organization import Organization
from src.app.models.organization_member import OrganizationMember
from src.app.models.student_enrollment import StudentEnrollment
from src.app.models.user import User
from src.app.schemas.invitation import (
    InvitationAccept,
    InvitationAcceptResult,
    InvitationPreview,
)
from src.app.schemas.org import ImportLine, ImportReport, InvitationRead
from src.app.schemas.organization import OrganizationSummary
from src.app.services import audit_service, auth_service, organization_service, user_service
from src.app.services.audit_service import RequestMeta

logger = logging.getLogger(__name__)

INVITATION_TTL_DAYS = 14
MAX_CSV_BYTES = 1_000_000
MAX_CSV_ROWS = 1000
_email_adapter = TypeAdapter(EmailStr)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _effective_status(invitation: Invitation) -> InvitationStatus:
    if invitation.status == InvitationStatus.PENDING and invitation.expires_at <= datetime.now(UTC):
        return InvitationStatus.EXPIRED
    return invitation.status


def _read(invitation: Invitation) -> InvitationRead:
    read = InvitationRead.model_validate(invitation)
    read.status = _effective_status(invitation)
    return read


def _log_link(email: str, token: str) -> None:
    logger.info("[DEV] invitation link for %s: /invitations/%s", email, token)


async def _issue(
    db: AsyncSession,
    organization_id: uuid.UUID,
    email: str,
    kind: InvitationKind,
    invited_by: uuid.UUID,
    *,
    org_role: OrgRole | None = None,
    from_csv: bool = False,
) -> tuple[Invitation, str, bool]:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=INVITATION_TTL_DAYS)
    invitation = await db.scalar(
        select(Invitation).where(
            Invitation.organization_id == organization_id,
            Invitation.email == email,
            Invitation.kind == kind,
            Invitation.status == InvitationStatus.PENDING,
        )
    )
    resent = invitation is not None
    if resent:
        invitation.token_hash = _hash(token)
        invitation.expires_at = expires_at
        invitation.org_role = org_role
        invitation.invited_by = invited_by
        invitation.from_csv = from_csv
    else:
        invitation = Invitation(
            organization_id=organization_id,
            email=email,
            kind=kind,
            org_role=org_role,
            token_hash=_hash(token),
            expires_at=expires_at,
            invited_by=invited_by,
            from_csv=from_csv,
        )
        db.add(invitation)
    await db.flush()
    return invitation, token, resent


async def _student_obstacle(db: AsyncSession, organization_id: uuid.UUID, email: str) -> str | None:
    user = await db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None:
        return None
    if user.account_type != AccountType.STUDENT:
        return "not_a_student"
    if await db.scalar(
        select(StudentEnrollment.id).where(
            StudentEnrollment.student_id == user.id,
            StudentEnrollment.organization_id == organization_id,
            StudentEnrollment.status == EnrollmentStatus.ACTIVE,
        )
    ):
        return "already_member"
    return None


async def invite_student(
    db: AsyncSession, actor: Actor, email: str, meta: RequestMeta
) -> InvitationRead:
    email = email.lower()
    obstacle = await _student_obstacle(db, actor.organization_id, email)
    if obstacle == "not_a_student":
        raise ConflictError("This email belongs to a staff account", code="NOT_A_STUDENT")
    if obstacle == "already_member":
        raise ConflictError("This student is already enrolled", code="ALREADY_MEMBER")

    invitation, token, resent = await _issue(
        db, actor.organization_id, email, InvitationKind.STUDENT, actor.user.id
    )
    audit_service.record(
        db,
        actor=actor.user,
        action="invitation.resend" if resent else "invitation.create",
        target_type="invitation",
        target_id=invitation.id,
        organization_id=actor.organization_id,
        changes={"kind": InvitationKind.STUDENT.value},
        meta=meta,
    )
    await db.commit()
    _log_link(email, token)
    await db.refresh(invitation)
    return _read(invitation)


async def invite_staff(
    db: AsyncSession, actor: Actor, email: str, org_role: OrgRole, meta: RequestMeta
) -> InvitationRead:
    email = email.lower()
    user = await db.scalar(select(User).where(func.lower(User.email) == email))
    if user and (
        user.account_type != AccountType.ORG_STAFF
        or await db.scalar(
            select(OrganizationMember.id).where(OrganizationMember.user_id == user.id)
        )
    ):
        raise ConflictError("This email already belongs to another account", code="ACCOUNT_EXISTS")

    invitation, token, resent = await _issue(
        db,
        actor.organization_id,
        email,
        InvitationKind.STAFF,
        actor.user.id,
        org_role=org_role,
    )
    audit_service.record(
        db,
        actor=actor.user,
        action="invitation.resend" if resent else "invitation.create",
        target_type="invitation",
        target_id=invitation.id,
        organization_id=actor.organization_id,
        changes={"kind": InvitationKind.STAFF.value, "org_role": org_role.value},
        meta=meta,
    )
    await db.commit()
    _log_link(email, token)
    await db.refresh(invitation)
    return _read(invitation)


def _parse_csv(content: bytes) -> list[tuple[int, str]]:
    if len(content) > MAX_CSV_BYTES:
        raise StudaFlyException("The file is too large (1 MB max)", "FILE_TOO_LARGE", 413)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise StudaFlyException("The file must be UTF-8 encoded", "INVALID_CSV", 422) from exc

    first_line = text.splitlines()[0] if text.strip() else ""
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    columns = {name.strip().lower(): name for name in reader.fieldnames or []}
    if "email" not in columns:
        raise StudaFlyException("The file needs an 'email' column", "INVALID_CSV", 422)

    rows = [
        (line, (row.get(columns["email"]) or "").strip().lower())
        for line, row in enumerate(reader, start=2)
    ]
    if len(rows) > MAX_CSV_ROWS:
        raise StudaFlyException(
            f"The file has more than {MAX_CSV_ROWS} rows", "FILE_TOO_LARGE", 413
        )
    return rows


async def import_csv(
    db: AsyncSession, actor: Actor, content: bytes, meta: RequestMeta
) -> ImportReport:
    rows = _parse_csv(content)
    lines: list[ImportLine] = []
    tokens: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line, email in rows:
        try:
            _email_adapter.validate_python(email)
        except ValidationError:
            lines.append(ImportLine(line=line, email=email or None, status="invalid_email"))
            continue
        if email in seen:
            lines.append(ImportLine(line=line, email=email, status="duplicate"))
            continue
        seen.add(email)
        obstacle = await _student_obstacle(db, actor.organization_id, email)
        if obstacle:
            lines.append(ImportLine(line=line, email=email, status=obstacle))
            continue
        _, token, resent = await _issue(
            db,
            actor.organization_id,
            email,
            InvitationKind.STUDENT,
            actor.user.id,
            from_csv=True,
        )
        tokens.append((email, token))
        lines.append(ImportLine(line=line, email=email, status="resent" if resent else "invited"))

    report = ImportReport(
        invited=sum(1 for item in lines if item.status == "invited"),
        resent=sum(1 for item in lines if item.status == "resent"),
        skipped=sum(1 for item in lines if item.status not in ("invited", "resent")),
        lines=lines,
    )
    audit_service.record(
        db,
        actor=actor.user,
        action="invitation.import",
        target_type="organization",
        target_id=actor.organization_id,
        organization_id=actor.organization_id,
        changes={"invited": report.invited, "resent": report.resent, "skipped": report.skipped},
        meta=meta,
    )
    await db.commit()
    for email, token in tokens:
        _log_link(email, token)
    return report


async def list_invitations(
    db: AsyncSession,
    actor: Actor,
    status: InvitationStatus | None,
    kind: InvitationKind | None,
) -> list[InvitationRead]:
    query = select(Invitation).where(Invitation.organization_id == actor.organization_id)
    if actor.org_role != OrgRole.MANAGER:
        kind = InvitationKind.STUDENT
    if kind:
        query = query.where(Invitation.kind == kind)
    invitations = [_read(i) for i in await db.scalars(query.order_by(Invitation.created_at.desc()))]
    return [i for i in invitations if status is None or i.status == status]


async def revoke(
    db: AsyncSession, actor: Actor, invitation_id: uuid.UUID, meta: RequestMeta
) -> None:
    invitation = await db.scalar(
        select(Invitation).where(
            Invitation.id == invitation_id,
            Invitation.organization_id == actor.organization_id,
        )
    )
    if not invitation:
        raise NotFoundError("Invitation not found")
    if invitation.kind == InvitationKind.STAFF and actor.org_role != OrgRole.MANAGER:
        raise ForbiddenError("Only a manager can revoke a staff invitation")
    if _effective_status(invitation) != InvitationStatus.PENDING:
        raise ConflictError("This invitation is no longer pending", code="INVITATION_NOT_PENDING")

    invitation.status = InvitationStatus.REVOKED
    audit_service.record(
        db,
        actor=actor.user,
        action="invitation.revoke",
        target_type="invitation",
        target_id=invitation.id,
        organization_id=actor.organization_id,
        changes={"kind": invitation.kind.value},
        meta=meta,
    )
    await db.commit()


async def _by_token(
    db: AsyncSession, token: str, *, lock: bool = False
) -> tuple[Invitation, Organization]:
    query = (
        select(Invitation, Organization)
        .join(Organization, Organization.id == Invitation.organization_id)
        .where(Invitation.token_hash == _hash(token))
    )
    if lock:
        query = query.with_for_update(of=Invitation)
    row = (await db.execute(query)).first()
    if not row:
        raise NotFoundError("This invitation does not exist")
    return row[0], row[1]


async def preview(db: AsyncSession, token: str) -> InvitationPreview:
    invitation, organization = await _by_token(db, token)
    return InvitationPreview(
        organization=OrganizationSummary.model_validate(organization),
        kind=invitation.kind,
        org_role=invitation.org_role,
        email=invitation.email,
        status=_effective_status(invitation),
        expires_at=invitation.expires_at,
    )


async def accept(
    db: AsyncSession,
    token: str,
    current_user: User | None,
    payload: InvitationAccept,
    meta: RequestMeta,
) -> InvitationAcceptResult:
    invitation, organization = await _by_token(db, token, lock=True)
    status = _effective_status(invitation)
    if status != InvitationStatus.PENDING:
        raise ConflictError(f"This invitation is {status.value}", code="INVITATION_NOT_PENDING")
    if organization.status != OrganizationStatus.ACTIVE:
        raise ConflictError("This school is not active", code="ORGANIZATION_INACTIVE")
    if current_user and current_user.email.lower() != invitation.email:
        raise ForbiddenError("This invitation was sent to another email address")

    if invitation.kind == InvitationKind.STUDENT:
        if current_user is None:
            raise UnauthorizedError("Sign in or create your student account first")
        await organization_service.enroll_student(
            db,
            current_user,
            organization.id,
            current_user.id,
            EnrollmentSource.CSV_IMPORT if invitation.from_csv else EnrollmentSource.INVITATION,
            meta,
            commit=False,
        )
        user, auth = current_user, None
    else:
        user = await _staff_account(db, current_user, invitation, payload)
        member = OrganizationMember(
            organization_id=organization.id, user_id=user.id, org_role=invitation.org_role
        )
        db.add(member)
        await db.flush()
        audit_service.record(
            db,
            actor=user,
            action="member.create",
            target_type="member",
            target_id=member.id,
            organization_id=organization.id,
            changes={"org_role": invitation.org_role.value, "via": "invitation"},
            meta=meta,
        )

    invitation.status = InvitationStatus.ACCEPTED
    invitation.accepted_at = datetime.now(UTC)
    if invitation.kind == InvitationKind.STAFF:
        await auth_service.revoke_all_sessions(user)
    await db.commit()
    if invitation.kind == InvitationKind.STAFF:
        auth = await auth_service.issue_tokens(db, user)
    return InvitationAcceptResult(
        kind=invitation.kind,
        organization=OrganizationSummary.model_validate(organization),
        auth=auth,
    )


async def _staff_account(
    db: AsyncSession,
    current_user: User | None,
    invitation: Invitation,
    payload: InvitationAccept,
) -> User:
    if current_user:
        if current_user.account_type != AccountType.ORG_STAFF or await db.scalar(
            select(OrganizationMember.id).where(OrganizationMember.user_id == current_user.id)
        ):
            raise ConflictError("This account cannot join a school team", code="ACCOUNT_EXISTS")
        return current_user

    if await db.scalar(select(User.id).where(func.lower(User.email) == invitation.email)):
        raise ConflictError(
            "An account already exists for this email: sign in first", code="ACCOUNT_EXISTS"
        )
    if not payload.name or not payload.password:
        raise StudaFlyException(
            "Name and password are required to create your account", "VALIDATION_ERROR", 422
        )
    user = await user_service.create_account(
        db, invitation.email, payload.name, AccountType.ORG_STAFF
    )
    user.password_hash = hash_password(payload.password)
    user.email_verified = True
    return user
