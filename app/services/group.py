from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.db.models.group import Group
from app.schemas.group import GroupCreate, GroupUpdate

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_group(db: AsyncSession, group_id: int) -> Optional[Group]:
    """
    Get a group by ID
    """
    result = await db.execute(select(Group).filter(Group.id == group_id))
    return result.scalars().first()


async def get_group_by_name(db: AsyncSession, name: str) -> Optional[Group]:
    """
    Get a group by name
    """
    result = await db.execute(select(Group).filter(Group.name == name))
    return result.scalars().first()


async def get_groups(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    active: Optional[bool] = None,
    backfill: Optional[bool] = None,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get multiple groups with pagination and optional filtering
    """
    query = select(Group)

    # Filter by active status if specified
    if active is not None:
        query = query.filter(Group.active == active)

    # Filter by backfill status if specified
    if backfill is not None:
        query = query.filter(Group.backfill == backfill)

    # Filter by search term if specified
    if search:
        query = query.filter(Group.name.ilike(f"%{search}%"))

    # Get total count for pagination
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Apply pagination
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()

    return {"items": items, "total": total}


async def create_group(db: AsyncSession, group_in: GroupCreate) -> Group:
    """
    Create a new group
    """
    # Check if group with name already exists
    existing_group = await get_group_by_name(db, name=group_in.name)
    if existing_group:
        raise ValueError("Group with this name already exists")

    # Create new group
    db_group = Group(
        name=group_in.name,
        description=group_in.description,
        active=group_in.active,
        backfill=group_in.backfill,
        min_files=group_in.min_files,
        min_size=group_in.min_size,
    )
    db.add(db_group)
    await db.commit()
    await db.refresh(db_group)
    return db_group


async def update_group(
    db: AsyncSession, group_id: int, group_in: GroupUpdate
) -> Optional[Group]:
    """
    Update a group
    """
    db_group = await get_group(db, group_id)
    if not db_group:
        return None

    # Update group fields
    update_data = group_in.dict(exclude_unset=True)

    # Update group object
    for field, value in update_data.items():
        setattr(db_group, field, value)

    db_group.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(db_group)
    return db_group


async def delete_group(db: AsyncSession, group_id: int) -> Optional[Group]:
    """
    Delete a group
    """
    db_group = await get_group(db, group_id)
    if not db_group:
        return None

    await db.delete(db_group)
    await db.commit()
    return db_group


async def update_group_article_stats(
    db: AsyncSession,
    group_id: int,
    first_article_id: Optional[int] = None,
    last_article_id: Optional[int] = None,
    current_article_id: Optional[int] = None,
) -> Optional[Group]:
    """
    Update group article statistics
    """
    db_group = await get_group(db, group_id)
    if not db_group:
        return None

    if first_article_id is not None:
        db_group.first_article_id = first_article_id

    if last_article_id is not None:
        db_group.last_article_id = last_article_id

    if current_article_id is not None:
        db_group.current_article_id = current_article_id

    db_group.last_updated = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(db_group)
    return db_group


async def update_group_backfill_target(
    db: AsyncSession, group_id: int, backfill_target: int
) -> Optional[Group]:
    """
    Update group backfill target
    """
    db_group = await get_group(db, group_id)
    if not db_group:
        return None

    db_group.backfill_target = backfill_target
    db_group.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(db_group)
    return db_group
