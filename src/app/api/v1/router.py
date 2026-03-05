from fastapi import APIRouter

from src.app.api.v1 import (
    admin,
    auth,
    budget,
    checklist,
    documents,
    guide,
    mobilities,
    notifications,
    timeline,
    users,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(mobilities.router, prefix="/mobilities", tags=["Mobilities"])
api_router.include_router(timeline.router, prefix="/mobilities", tags=["Timeline"])
api_router.include_router(checklist.router, prefix="/mobilities", tags=["Checklist"])
api_router.include_router(budget.router, prefix="/destinations", tags=["Budget"])
api_router.include_router(guide.router, prefix="/destinations", tags=["Guide"])
api_router.include_router(documents.router, prefix="", tags=["Documents"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
