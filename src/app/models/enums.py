from enum import StrEnum

from sqlalchemy import Enum


class AccountType(StrEnum):
    STUDENT = "student"
    ORG_STAFF = "org_staff"
    PLATFORM_ADMIN = "platform_admin"


class UserStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING_DELETION = "pending_deletion"


class OrganizationStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class OrgRole(StrEnum):
    MANAGER = "manager"
    ADVISOR = "advisor"


class EnrollmentStatus(StrEnum):
    ACTIVE = "active"
    LEFT = "left"
    REVOKED = "revoked"


class EnrollmentSource(StrEnum):
    INVITATION = "invitation"
    CSV_IMPORT = "csv_import"
    JOIN_CODE = "join_code"
    ADMIN = "admin"
    MIGRATION = "migration"


class InvitationKind(StrEnum):
    STUDENT = "student"
    STAFF = "staff"


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ContractStatus(StrEnum):
    PILOT = "pilot"
    ACTIVE = "active"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class PremiumSource(StrEnum):
    PURCHASE = "purchase"
    ADMIN_GRANT = "admin_grant"


class NotificationType(StrEnum):
    TASK_DUE_SOON = "task_due_soon"
    TASK_DUE_TODAY = "task_due_today"
    TASK_OVERDUE = "task_overdue"
    ORGANIZATION_INVITATION = "organization_invitation"
    INVITATION_ACCEPTED = "invitation_accepted"


class PushPlatform(StrEnum):
    IOS = "ios"
    ANDROID = "android"


def pg_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        values_callable=lambda cls: [member.value for member in cls],
        validate_strings=True,
    )
