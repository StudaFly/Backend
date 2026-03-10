from fastapi import APIRouter

router = APIRouter()


@router.get("/{destination_id}/guide")
async def get_guide(destination_id: str):
    # TODO: implement via guide_service
    raise NotImplementedError
