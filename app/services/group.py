from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.group import Group
from app.schemas.group import GroupCreate, GroupUpdate


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
    db: AsyncSession, skip: int = 0, limit: int = 100, active_only: bool = False
) -> List[Group]:
    """
    Get multiple groups with pagination and optional filtering
    """
    query = select(Group)

    if active_only:
        query = query.filter(Group.active == True)

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


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

    db_group.updated_at = datetime.utcnow()

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
    current_article_id: Optional[int] = None
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

    db_group.last_updated = datetime.utcnow()

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
    db_group.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(db_group)
    return db_group
