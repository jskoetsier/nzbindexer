from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_current_admin_user
from app.db.session import get_db
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services.user import (
    create_user,
    get_user,
    get_users,
    update_user,
    delete_user
)
from app.db.models.user import User

router = APIRouter()


@router.get("/", response_model=List[UserResponse])
async def read_users(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Retrieve users. Admin only.
    """
    users = await get_users(db, skip=skip, limit=limit)
    return users


@router.post("/", response_model=UserResponse)
async def create_new_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Create new user. Admin only.
    """
    user = await create_user(db, user_in)
    return user


@router.get("/me", response_model=UserResponse)
async def read_user_me(
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get current user.
    """
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_user_me(
    user_in: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Update current user.
    """
    user = await update_user(db, current_user.id, user_in)
    return user


@router.get("/{user_id}", response_model=UserResponse)
async def read_user_by_id(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get a specific user by id.
    """
    user = await get_user(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    if user.id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user_by_id(
    user_id: int,
    user_in: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Update a user. Admin only.
    """
    user = await get_user(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    user = await update_user(db, user_id, user_in)
    return user


@router.delete("/{user_id}", response_model=UserResponse)
async def delete_user_by_id(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Delete a user. Admin only.
    """
    user = await get_user(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    user = await delete_user(db, user_id)
    return user
