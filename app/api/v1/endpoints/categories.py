from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_current_admin_user
from app.db.session import get_db
from app.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate, CategoryWithChildren
from app.services.category import (
    create_category,
    get_category,
    get_categories,
    get_categories_with_children,
    update_category,
    delete_category
)
from app.db.models.user import User

router = APIRouter()


@router.get("/", response_model=List[CategoryResponse])
async def read_categories(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Retrieve categories.
    """
    categories = await get_categories(db, skip=skip, limit=limit)
    return categories


@router.get("/tree", response_model=List[CategoryWithChildren])
async def read_categories_tree(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Retrieve categories as a tree structure.
    """
    categories = await get_categories_with_children(db)
    return categories


@router.post("/", response_model=CategoryResponse)
async def create_new_category(
    category_in: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Create new category. Admin only.
    """
    category = await create_category(db, category_in)
    return category


@router.get("/{category_id}", response_model=CategoryResponse)
async def read_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get a specific category by id.
    """
    category = await get_category(db, category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )
    return category


@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category_by_id(
    category_id: int,
    category_in: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Update a category. Admin only.
    """
    category = await get_category(db, category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )
    category = await update_category(db, category_id, category_in)
    return category


@router.delete("/{category_id}", response_model=CategoryResponse)
async def delete_category_by_id(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Delete a category. Admin only.
    """
    category = await get_category(db, category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )
    category = await delete_category(db, category_id)
    return category
