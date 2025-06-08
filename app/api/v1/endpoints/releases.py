from typing import Any, Dict, List, Optional

from app.api.deps import get_current_active_user, get_current_admin_user
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.release import Release, ReleaseCreate, ReleaseList, ReleaseUpdate
from app.services.nzb import get_nzb_for_release
from app.services.release import (
    create_release,
    delete_release,
    get_release,
    get_releases,
    process_release,
    update_release,
)

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/", response_model=ReleaseList)
async def read_releases(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    group_id: Optional[int] = None,
    sort_by: str = "added_date",
    sort_desc: bool = True,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Retrieve releases with optional filtering.
    """
    releases = await get_releases(
        db,
        skip=skip,
        limit=limit,
        search=search,
        category_id=category_id,
        group_id=group_id,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )
    return releases


@router.get("/search", response_model=ReleaseList)
async def search_releases_endpoint(
    query: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    category_id: Optional[int] = None,
    group_id: Optional[int] = None,
    sort_by: str = "added_date",
    sort_desc: bool = True,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Search releases by name or search_name.
    """
    releases = await get_releases(
        db,
        skip=skip,
        limit=limit,
        search=query,
        category_id=category_id,
        group_id=group_id,
        sort_by=sort_by,
        sort_desc=sort_desc,
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


@router.get("/{release_id}", response_model=Release)
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


@router.put("/{release_id}", response_model=Release)
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


@router.delete("/{release_id}", response_model=Dict[str, bool])
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
    success = await delete_release(db, release_id)
    return {"success": success}


@router.post("/{release_id}/process", response_model=Release)
async def process_release_endpoint(
    release_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Process a release to extract metadata and categorize it.
    """
    release = await get_release(db, release_id)
    if not release:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Release not found",
        )
    processed_release = await process_release(db, release_id)
    if not processed_release:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process release",
        )
    return processed_release


@router.get("/{release_id}/download")
async def download_release_nzb(
    release_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Download the NZB file for a release.
    """
    # Get release
    release = await get_release(db, release_id)
    if not release:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Release not found",
        )

    # Get NZB file
    nzb_path = await get_nzb_for_release(db, release_id)
    if not nzb_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="NZB file not found",
        )

    # Increment grab count
    # TODO: Implement increment_grab_count
    # await increment_grab_count(db, release_id, current_user.id)

    # Return NZB file
    filename = f"{release.name.replace(' ', '_')}.nzb"
    return FileResponse(
        path=nzb_path, filename=filename, media_type="application/x-nzb"
    )
