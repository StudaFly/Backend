from fastapi import APIRouter

router = APIRouter()


@router.get("/students")
async def list_students():
    # TODO: return students via admin_service.list_students()
    raise NotImplementedError


@router.get("/stats")
async def get_stats():
    # TODO: return stats via admin_service.get_stats()
    raise NotImplementedError


@router.post("/tasks", status_code=201)
async def create_global_task():
    # TODO: create global task via admin_service.create_global_task()
    raise NotImplementedError
