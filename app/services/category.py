from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.category import Category
from app.schemas.category import CategoryCreate, CategoryUpdate


async def get_category(db: AsyncSession, category_id: int) -> Optional[Category]:
    """
    Get a category by ID
    """
    result = await db.execute(select(Category).filter(Category.id == category_id))
    return result.scalars().first()


async def get_category_by_name(db: AsyncSession, name: str) -> Optional[Category]:
    """
    Get a category by name
    """
    result = await db.execute(select(Category).filter(Category.name == name))
    return result.scalars().first()


async def get_categories(
    db: AsyncSession, skip: int = 0, limit: int = 100, active_only: bool = False
) -> List[Category]:
    """
    Get multiple categories with pagination and optional filtering
    """
    query = select(Category)

    if active_only:
        query = query.filter(Category.active == True)

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


async def get_root_categories(
    db: AsyncSession, active_only: bool = False
) -> List[Category]:
    """
    Get root categories (categories without a parent)
    """
    query = select(Category).filter(Category.parent_id == None)

    if active_only:
        query = query.filter(Category.active == True)

    result = await db.execute(query)
    return result.scalars().all()


async def get_child_categories(
    db: AsyncSession, parent_id: int, active_only: bool = False
) -> List[Category]:
    """
    Get child categories for a specific parent
    """
    query = select(Category).filter(Category.parent_id == parent_id)

    if active_only:
        query = query.filter(Category.active == True)

    result = await db.execute(query)
    return result.scalars().all()


async def get_categories_with_children(
    db: AsyncSession, active_only: bool = False
) -> List[Category]:
    """
    Get categories organized in a tree structure
    """
    # Get root categories
    root_categories = await get_root_categories(db, active_only)

    # For each root category, recursively get its children
    for category in root_categories:
        await _populate_children(db, category, active_only)

    return root_categories


async def _populate_children(
    db: AsyncSession, category: Category, active_only: bool = False
) -> None:
    """
    Helper function to recursively populate children for a category
    """
    children = await get_child_categories(db, category.id, active_only)
    category.children = children

    for child in children:
        await _populate_children(db, child, active_only)


async def create_category(db: AsyncSession, category_in: CategoryCreate) -> Category:
    """
    Create a new category
    """
    # Check if category with name already exists
    existing_category = await get_category_by_name(db, name=category_in.name)
    if existing_category:
        raise ValueError("Category with this name already exists")

    # If parent_id is provided, check if parent exists
    if category_in.parent_id:
        parent = await get_category(db, category_in.parent_id)
        if not parent:
            raise ValueError("Parent category not found")

    # Create new category
    db_category = Category(
        name=category_in.name,
        description=category_in.description,
        active=category_in.active,
        icon=category_in.icon,
        color=category_in.color,
        sort_order=category_in.sort_order,
        parent_id=category_in.parent_id,
    )
    db.add(db_category)
    await db.commit()
    await db.refresh(db_category)
    return db_category


async def update_category(
    db: AsyncSession, category_id: int, category_in: CategoryUpdate
) -> Optional[Category]:
    """
    Update a category
    """
    db_category = await get_category(db, category_id)
    if not db_category:
        return None

    # Update category fields
    update_data = category_in.dict(exclude_unset=True)

    # If parent_id is provided, check if parent exists and prevent circular references
    if "parent_id" in update_data and update_data["parent_id"]:
        # Check if parent exists
        parent = await get_category(db, update_data["parent_id"])
        if not parent:
            raise ValueError("Parent category not found")

        # Prevent setting parent to self
        if update_data["parent_id"] == category_id:
            raise ValueError("Category cannot be its own parent")

        # Prevent circular references
        current_parent = parent
        while current_parent:
            if current_parent.id == category_id:
                raise ValueError("Circular reference detected in category hierarchy")

            if current_parent.parent_id:
                current_parent = await get_category(db, current_parent.parent_id)
            else:
                current_parent = None

    # Update category object
    for field, value in update_data.items():
        setattr(db_category, field, value)

    db_category.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(db_category)
    return db_category


async def delete_category(db: AsyncSession, category_id: int) -> Optional[Category]:
    """
    Delete a category
    """
    db_category = await get_category(db, category_id)
    if not db_category:
        return None

    # Check if category has children
    children = await get_child_categories(db, category_id)
    if children:
        raise ValueError("Cannot delete category with children")

    await db.delete(db_category)
    await db.commit()
    return db_category
