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


def pg_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        values_callable=lambda cls: [member.value for member in cls],
        validate_strings=True,
    )
