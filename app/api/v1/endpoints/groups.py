from typing import Any, Dict, List

from app.api.deps import get_current_active_user, get_current_admin_user
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.group import GroupCreate, GroupResponse, GroupUpdate
from app.schemas.newsgroup_discovery import (
    NewsgroupDiscoveryRequest,
    NewsgroupDiscoveryResponse,
)
from app.services.group import (
    create_group,
    delete_group,
    get_group,
    get_groups,
    update_group,
)
from app.services.nntp import discover_newsgroups

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/", response_model=List[GroupResponse])
async def read_groups(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Retrieve groups.
    """
    groups = await get_groups(db, skip=skip, limit=limit)
    return groups


@router.post("/", response_model=GroupResponse)
async def create_new_group(
    group_in: GroupCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Create new group. Admin only.
    """
    group = await create_group(db, group_in)
    return group


@router.get("/{group_id}", response_model=GroupResponse)
async def read_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get a specific group by id.
    """
    group = await get_group(db, group_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found",
        )
    return group


@router.put("/{group_id}", response_model=GroupResponse)
async def update_group_by_id(
    group_id: int,
    group_in: GroupUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Update a group. Admin only.
    """
    group = await get_group(db, group_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found",
        )
    group = await update_group(db, group_id, group_in)
    return group


@router.patch("/{group_id}", response_model=GroupResponse)
async def patch_group_by_id(
    group_id: int,
    group_in: GroupUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Partially update a group. Admin only.
    """
    group = await get_group(db, group_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found",
        )
    group = await update_group(db, group_id, group_in)
    return group


@router.delete("/{group_id}", response_model=GroupResponse)
async def delete_group_by_id(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Delete a group. Admin only.
    """
    group = await get_group(db, group_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found",
        )
    group = await delete_group(db, group_id)
    return group


@router.post("/discover", response_model=NewsgroupDiscoveryResponse)
async def discover_groups(
    discovery_request: NewsgroupDiscoveryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Discover newsgroups from NNTP server and add them to the database. Admin only.
    """
    try:
        stats = await discover_newsgroups(
            db, pattern=discovery_request.pattern, active=discovery_request.active
        )
        return stats
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to discover newsgroups: {str(e)}",
        )
