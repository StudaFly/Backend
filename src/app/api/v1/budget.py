from fastapi import APIRouter

router = APIRouter()


@router.get("/{destination_id}/budget")
async def get_budget(destination_id: str):
    # TODO: return budget via budget_service.get_budget_estimate()
    raise NotImplementedError
