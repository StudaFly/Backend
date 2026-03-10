from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.dependencies import get_current_user
from src.app.db.session import get_db
from src.app.models.user import User
from src.app.schemas.common import ResponseBase
from src.app.schemas.task import TaskCreate, TaskRead, TaskUpdate
from src.app.services import checklist_service

router = APIRouter()


@router.get("/{mobility_id}/tasks", response_model=ResponseBase[list[TaskRead]])
async def list_tasks(
    mobility_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResponseBase[list[TaskRead]]:
    tasks = await checklist_service.list_tasks(db, user_id=current_user.id, mobility_id=mobility_id)
    return ResponseBase(data=tasks, message="Tasks retrieved successfully")


@router.post("/{mobility_id}/tasks", response_model=ResponseBase[TaskRead], status_code=201)
async def create_task(
    mobility_id: UUID,
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResponseBase[TaskRead]:
    task = await checklist_service.create_task(
        db, user_id=current_user.id, mobility_id=mobility_id, payload=payload
    )
    return ResponseBase(data=task, message="Task created successfully")


@router.patch("/tasks/{task_id}", response_model=ResponseBase[TaskRead])
async def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResponseBase[TaskRead]:
    task = await checklist_service.update_task(
        db, user_id=current_user.id, task_id=task_id, payload=payload
    )
    return ResponseBase(data=task, message="Task updated successfully")


@router.patch("/tasks/{task_id}/complete", response_model=ResponseBase[TaskRead])
async def complete_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResponseBase[TaskRead]:
    task = await checklist_service.complete_task(db, user_id=current_user.id, task_id=task_id)
    return ResponseBase(data=task, message="Task marked as completed")


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    await checklist_service.delete_task(db, user_id=current_user.id, task_id=task_id)
