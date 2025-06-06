from app.api.v1.endpoints import auth, categories, groups, nntp, releases, users
from fastapi import APIRouter

api_router = APIRouter()

# Include all API endpoint routers
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(groups.router, prefix="/groups", tags=["groups"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(releases.router, prefix="/releases", tags=["releases"])
api_router.include_router(nntp.router, prefix="/nntp", tags=["nntp"])
