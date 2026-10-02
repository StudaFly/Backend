from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core import reference
from src.app.db.session import get_db
from src.app.schemas.common import ResponseBase
from src.app.schemas.reference import PublicStats, ReferenceData
from src.app.services import stats_service

router = APIRouter()


@router.get("/health")
async def health():
    from src.app.core.services_status import (
        CACHE_TARGET,
        DATABASE_TARGET,
        START_HINT,
        check_cache,
        check_database,
    )

    services = {
        "database": "ok" if await check_database() else "unreachable",
        "cache": "ok" if await check_cache() else "unreachable",
    }
    if all(value == "ok" for value in services.values()):
        return {"data": {"status": "healthy", "services": services}, "message": "OK"}

    down = [
        f"{name} ({DATABASE_TARGET if name == 'database' else CACHE_TARGET})"
        for name, value in services.items()
        if value != "ok"
    ]
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "SERVICE_UNAVAILABLE",
                "message": f"Unreachable: {', '.join(down)}. {START_HINT}",
                "details": services,
            }
        },
    )


@router.get("/reference", response_model=ResponseBase[ReferenceData])
async def get_reference() -> ResponseBase[ReferenceData]:
    data = ReferenceData(
        mobility_types=reference.MOBILITY_TYPES,
        task_categories=reference.TASK_CATEGORIES,
        task_priorities=reference.TASK_PRIORITIES,
        avatar_emojis=reference.AVATAR_EMOJIS,
    )
    return ResponseBase(data=data, message="OK")


@router.get("/stats", response_model=ResponseBase[PublicStats])
async def get_stats(db: AsyncSession = Depends(get_db)) -> ResponseBase[PublicStats]:
    return ResponseBase(data=await stats_service.get_public_stats(db), message="OK")
