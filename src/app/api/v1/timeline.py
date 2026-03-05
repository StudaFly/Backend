from fastapi import APIRouter

router = APIRouter()


@router.get("/{mobility_id}/timeline")
async def get_timeline(mobility_id: str):
    # TODO: return timeline via timeline_service.get_timeline()
    raise NotImplementedError
