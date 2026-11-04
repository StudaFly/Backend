import uuid
from datetime import date, timedelta
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.exceptions import ConflictError, NotFoundError, StudaFlyException
from src.app.models.contract import Contract
from src.app.models.enums import ContractStatus, EnrollmentStatus
from src.app.models.organization import Organization
from src.app.models.student_enrollment import StudentEnrollment
from src.app.models.user import User
from src.app.schemas.org import OrgContractRead, OrgContractTerms
from src.app.schemas.platform_admin import ContractCreate, ContractRead, ContractUpdate
from src.app.services import audit_service
from src.app.services.audit_service import RequestMeta
from src.app.services.entitlements import CURRENT_CONTRACT_STATUSES


class ContractState(StrEnum):
    NONE = "none"
    CURRENT = "current"
    READ_ONLY = "read_only"
    BLOCKED = "blocked"


async def contract_state(
    db: AsyncSession, organization_id: uuid.UUID, today: date | None = None
) -> tuple[ContractState, Contract | None]:
    today = today or date.today()
    contracts = list(
        await db.scalars(
            select(Contract)
            .where(Contract.organization_id == organization_id)
            .order_by(Contract.start_date.desc(), Contract.created_at.desc())
        )
    )
    if not contracts:
        return ContractState.NONE, None
    for contract in contracts:
        if contract.status in CURRENT_CONTRACT_STATUSES and (
            contract.start_date <= today <= contract.end_date
        ):
            return ContractState.CURRENT, contract
    started = [c for c in contracts if c.start_date <= today]
    if not started:
        return ContractState.NONE, contracts[0]
    latest = started[0]
    if latest.status in (ContractStatus.SUSPENDED, ContractStatus.CANCELLED):
        return ContractState.BLOCKED, latest
    return ContractState.READ_ONLY, latest


async def _active_students(db: AsyncSession, organization_id: uuid.UUID) -> int:
    return (
        await db.scalar(
            select(func.count(StudentEnrollment.id)).where(
                StudentEnrollment.organization_id == organization_id,
                StudentEnrollment.status == EnrollmentStatus.ACTIVE,
            )
        )
        or 0
    )


async def ensure_can_enroll(db: AsyncSession, organization_id: uuid.UUID) -> None:
    state, contract = await contract_state(db, organization_id)
    if state in (ContractState.READ_ONLY, ContractState.BLOCKED):
        raise ConflictError(
            "This school's contract no longer allows new students", code="CONTRACT_INACTIVE"
        )
    if state == ContractState.CURRENT and contract.student_quota is not None:
        if await _active_students(db, organization_id) >= contract.student_quota:
            raise ConflictError(
                f"The contract allows {contract.student_quota} students", code="QUOTA_EXCEEDED"
            )


async def org_contract(db: AsyncSession, organization_id: uuid.UUID) -> OrgContractRead:
    state, contract = await contract_state(db, organization_id)
    return OrgContractRead(
        state=state.value,
        contract=OrgContractTerms.model_validate(contract, from_attributes=True)
        if contract
        else None,
        active_students=await _active_students(db, organization_id),
    )


async def _lock_organization(db: AsyncSession, organization_id: uuid.UUID) -> None:
    if not await db.scalar(
        select(Organization.id).where(Organization.id == organization_id).with_for_update()
    ):
        raise NotFoundError("Organization not found")


def _validate(values: dict) -> None:
    if values["end_date"] < values["start_date"]:
        raise StudaFlyException("endDate must be after startDate", "VALIDATION_ERROR", 422)
    if values["status"] == ContractStatus.PILOT and values["price_cents"] != 0:
        raise StudaFlyException("A pilot contract is free", "VALIDATION_ERROR", 422)


async def _ensure_no_overlap(
    db: AsyncSession, organization_id: uuid.UUID, values: dict, exclude_id: uuid.UUID | None
) -> None:
    if values["status"] not in CURRENT_CONTRACT_STATUSES:
        return
    overlapping = await db.scalar(
        select(Contract.id).where(
            Contract.organization_id == organization_id,
            Contract.id != exclude_id,
            Contract.status.in_(CURRENT_CONTRACT_STATUSES),
            Contract.start_date <= values["end_date"],
            Contract.end_date >= values["start_date"],
        )
    )
    if overlapping:
        raise ConflictError(
            "Another pilot or active contract covers these dates", code="CONTRACT_OVERLAP"
        )


def _changes(before: dict, after: dict) -> dict:
    changes = {}
    for field, value in after.items():
        if before.get(field) != value:
            changes[field] = (
                "changed"
                if field == "notes"
                else [
                    str(before.get(field)) if before.get(field) is not None else None,
                    str(value) if value is not None else None,
                ]
            )
    return changes


async def create_contract(
    db: AsyncSession,
    actor: User,
    organization_id: uuid.UUID,
    payload: ContractCreate,
    meta: RequestMeta,
) -> ContractRead:
    await _lock_organization(db, organization_id)
    values = payload.model_dump()
    _validate(values)
    await _ensure_no_overlap(db, organization_id, values, None)

    contract = Contract(organization_id=organization_id, created_by=actor.id, **values)
    db.add(contract)
    await db.flush()
    audit_service.record(
        db,
        actor=actor,
        action="contract.create",
        target_type="contract",
        target_id=contract.id,
        organization_id=organization_id,
        changes=_changes({}, {k: v for k, v in values.items() if v is not None}),
        meta=meta,
    )
    await db.commit()
    await db.refresh(contract)
    return ContractRead.model_validate(contract)


async def update_contract(
    db: AsyncSession,
    actor: User,
    organization_id: uuid.UUID,
    contract_id: uuid.UUID,
    payload: ContractUpdate,
    meta: RequestMeta,
) -> ContractRead:
    await _lock_organization(db, organization_id)
    contract = await db.scalar(
        select(Contract).where(
            Contract.id == contract_id, Contract.organization_id == organization_id
        )
    )
    if not contract:
        raise NotFoundError("Contract not found")

    fields = ContractCreate.model_fields
    before = {field: getattr(contract, field) for field in fields}
    data = payload.model_dump(exclude_unset=True)
    values = {
        **before,
        **{k: v for k, v in data.items() if v is not None or k in ("student_quota", "notes")},
    }
    _validate(values)
    await _ensure_no_overlap(db, organization_id, values, contract.id)

    for field, value in values.items():
        setattr(contract, field, value)
    changes = _changes(before, values)
    if changes:
        audit_service.record(
            db,
            actor=actor,
            action="contract.update",
            target_type="contract",
            target_id=contract.id,
            organization_id=organization_id,
            changes=changes,
            meta=meta,
        )
    await db.commit()
    await db.refresh(contract)
    return ContractRead.model_validate(contract)


async def list_contracts(
    db: AsyncSession,
    *,
    page: int,
    per_page: int,
    organization_id: uuid.UUID | None = None,
    status: ContractStatus | None = None,
    expiring_within: int | None = None,
) -> tuple[list[ContractRead], int]:
    filters = []
    if organization_id:
        filters.append(Contract.organization_id == organization_id)
    if status:
        filters.append(Contract.status == status)
    if expiring_within is not None:
        today = date.today()
        filters += [
            Contract.status.in_(CURRENT_CONTRACT_STATUSES),
            Contract.end_date >= today,
            Contract.end_date <= today + timedelta(days=expiring_within),
        ]
    total = await db.scalar(select(func.count(Contract.id)).where(*filters))
    contracts = await db.scalars(
        select(Contract)
        .where(*filters)
        .order_by(Contract.end_date, Contract.id)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    return [ContractRead.model_validate(c) for c in contracts], total or 0


async def expire_contracts(db: AsyncSession, today: date | None = None) -> int:
    today = today or date.today()
    contracts = list(
        await db.scalars(
            select(Contract).where(
                Contract.status.in_(CURRENT_CONTRACT_STATUSES), Contract.end_date < today
            )
        )
    )
    for contract in contracts:
        audit_service.record(
            db,
            actor=None,
            action="contract.expire",
            target_type="contract",
            target_id=contract.id,
            organization_id=contract.organization_id,
            changes={"status": [contract.status.value, ContractStatus.EXPIRED.value]},
        )
        contract.status = ContractStatus.EXPIRED
    await db.commit()
    return len(contracts)
