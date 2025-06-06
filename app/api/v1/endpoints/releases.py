from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_current_admin_user
from app.db.session import get_db
from app.schemas.release import ReleaseCreate, ReleaseDetail, ReleaseResponse, ReleaseUpdate
from app.services.release import (
    create_release,
    get_release,
    get_releases,
    search_releases,
    update_release,
    delete_release,
    increment_grab_count
)
from app.db.models.user import User

router = APIRouter()


@router.get("/", response_model=List[ReleaseResponse])
async def read_releases(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    category_id: Optional[int] = None,
    group_id: Optional[int] = None,
    status: Optional[int] = None,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Retrieve releases with optional filtering.
    """
    releases = await get_releases(
        db,
        skip=skip,
        limit=limit,
        category_id=category_id,
        group_id=group_id,
        status=status
    )
    return releases


@router.get("/search", response_model=List[ReleaseResponse])
async def search_releases_endpoint(
    query: str = Query(..., min_length=3),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    category_id: Optional[int] = None,
    group_id: Optional[int] = None,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Search releases by name or search_name.
    """
    releases = await search_releases(
        db,
        query=query,
        skip=skip,
        limit=limit,
        category_id=category_id,
        group_id=group_id
    )
    return releases


@router.post("/", response_model=ReleaseResponse)
async def create_new_release(
    release_in: ReleaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Create new release. Admin only.
    """
    release = await create_release(db, release_in)
    return release


@router.get("/{release_id}", response_model=ReleaseDetail)
async def read_release(
    release_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get a specific release by id.
    """
    release = await get_release(db, release_id)
    if not release:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Release not found",
        )
    return release


@router.put("/{release_id}", response_model=ReleaseResponse)
async def update_release_by_id(
    release_id: int,
    release_in: ReleaseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Update a release. Admin only.
    """
    release = await get_release(db, release_id)
    if not release:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Release not found",
        )
    release = await update_release(db, release_id, release_in)
    return release


@router.delete("/{release_id}", response_model=ReleaseResponse)
async def delete_release_by_id(
    release_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Delete a release. Admin only.
    """
    release = await get_release(db, release_id)
    if not release:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Release not found",
        )
    release = await delete_release(db, release_id)
    return release


@router.post("/{release_id}/grab", response_model=ReleaseResponse)
async def grab_release(
    release_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Increment the grab count for a release.
    """
    release = await get_release(db, release_id)
    if not release:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Release not found",
        )
    release = await increment_grab_count(db, release_id, current_user.id)
    return release
