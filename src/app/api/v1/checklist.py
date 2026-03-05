from fastapi import APIRouter

router = APIRouter()


@router.get("/{mobility_id}/tasks")
async def list_tasks(mobility_id: str):
    # TODO: return tasks via checklist_service.list_tasks()
    raise NotImplementedError


@router.post("/{mobility_id}/tasks", status_code=201)
async def create_task(mobility_id: str):
    # TODO: create task via checklist_service.create_task()
    raise NotImplementedError


@router.patch("/tasks/{task_id}")
async def update_task(task_id: str):
    # TODO: update task via checklist_service.update_task()
    raise NotImplementedError


@router.patch("/tasks/{task_id}/complete")
async def complete_task(task_id: str):
    # TODO: complete task via checklist_service.complete_task()
    raise NotImplementedError


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: str):
    # TODO: delete task via checklist_service.delete_task()
    raise NotImplementedError
