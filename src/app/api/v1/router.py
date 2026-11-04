from fastapi import APIRouter

from src.app.api.v1 import (
    auth,
    budget,
    checklist,
    destinations,
    documents,
    guide,
    invitations,
    mobilities,
    notifications,
    org,
    organizations,
    platform_admin,
    reference,
    timeline,
    users,
)

api_router = APIRouter()

api_router.include_router(reference.router, tags=["Reference"])
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(mobilities.router, prefix="/mobilities", tags=["Mobilities"])
api_router.include_router(timeline.router, prefix="/mobilities", tags=["Timeline"])
api_router.include_router(checklist.mobility_router, prefix="/mobilities", tags=["Checklist"])
api_router.include_router(checklist.task_router, prefix="", tags=["Tasks"])
api_router.include_router(destinations.router, prefix="/destinations", tags=["Destinations"])
api_router.include_router(budget.router, prefix="/destinations", tags=["Budget"])
api_router.include_router(guide.router, prefix="/destinations", tags=["Guide"])
api_router.include_router(documents.router, prefix="", tags=["Documents"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
api_router.include_router(platform_admin.router, prefix="/admin", tags=["Platform admin"])
api_router.include_router(org.router, prefix="/org", tags=["Organization space"])
api_router.include_router(organizations.router, prefix="/organizations", tags=["Organizations"])
api_router.include_router(invitations.router, prefix="/invitations", tags=["Invitations"])
