from fastapi import APIRouter

router = APIRouter()


@router.get("/me")
async def get_me():
    # TODO: return current_user via user_service.get_by_id()
    raise NotImplementedError


@router.patch("/me")
async def update_me():
    # TODO: update current user via user_service.update()
    raise NotImplementedError


@router.delete("/me", status_code=204)
async def delete_me():
    # TODO: delete current user via user_service.delete()
    raise NotImplementedError
