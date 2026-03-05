from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_mobilities():
    # TODO: return mobilities via mobility_service.list_by_user()
    raise NotImplementedError


@router.post("/", status_code=201)
async def create_mobility():
    # TODO: create mobility via mobility_service.create()
    raise NotImplementedError


@router.get("/{mobility_id}")
async def get_mobility(mobility_id: str):
    # TODO: return mobility via mobility_service.get_by_id()
    raise NotImplementedError


@router.patch("/{mobility_id}")
async def update_mobility(mobility_id: str):
    # TODO: update mobility via mobility_service.update()
    raise NotImplementedError


@router.delete("/{mobility_id}", status_code=204)
async def delete_mobility(mobility_id: str):
    # TODO: delete mobility via mobility_service.delete()
    raise NotImplementedError
