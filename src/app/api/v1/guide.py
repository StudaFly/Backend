from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_destinations():
    # TODO: return destinations list
    raise NotImplementedError


@router.get("/{destination_id}/guide")
async def get_guide(destination_id: str):
    # TODO: return guide via guide_service.get_guide()
    raise NotImplementedError
