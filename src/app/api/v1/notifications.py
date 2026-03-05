from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_notifications():
    # TODO: return notifications via notification_service.list_notifications()
    raise NotImplementedError
