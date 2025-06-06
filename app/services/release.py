from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy import select, or_, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.models.release import Release
from app.db.models.category import Category
from app.db.models.group import Group
from app.schemas.release import ReleaseCreate, ReleaseUpdate


async def get_release(db: AsyncSession, release_id: int) -> Optional[Release]:
    """
    Get a release by ID with category and group relationships loaded
    """
    result = await db.execute(
        select(Release)
        .filter(Release.id == release_id)
        .options(
            joinedload(Release.category),
            joinedload(Release.group)
        )
    )
    return result.scalars().first()


async def get_release_by_guid(db: AsyncSession, guid: str) -> Optional[Release]:
    """
    Get a release by GUID
    """
    result = await db.execute(select(Release).filter(Release.guid == guid))
    return result.scalars().first()


async def get_releases(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    category_id: Optional[int] = None,
    group_id: Optional[int] = None,
    status: Optional[int] = None
) -> List[Release]:
    """
    Get multiple releases with pagination and optional filtering
    """
    query = select(Release)

    # Apply filters if provided
    filters = []
    if category_id is not None:
        filters.append(Release.category_id == category_id)

    if group_id is not None:
        filters.append(Release.group_id == group_id)

    if status is not None:
        filters.append(Release.status == status)

    if filters:
        query = query.filter(and_(*filters))

    # Order by added_date descending (newest first)
    query = query.order_by(desc(Release.added_date))

    # Apply pagination
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


async def search_releases(
    db: AsyncSession,
    query: str,
    skip: int = 0,
    limit: int = 100,
    category_id: Optional[int] = None,
    group_id: Optional[int] = None
) -> List[Release]:
    """
    Search releases by name or search_name
    """
    # Create search pattern with wildcards
    search_pattern = f"%{query}%"

    # Build query
    db_query = select(Release).filter(
        or_(
            Release.name.ilike(search_pattern),
            Release.search_name.ilike(search_pattern)
        )
    )

    # Apply additional filters if provided
    filters = []
    if category_id is not None:
        filters.append(Release.category_id == category_id)

    if group_id is not None:
        filters.append(Release.group_id == group_id)

    if filters:
        db_query = db_query.filter(and_(*filters))

    # Order by added_date descending (newest first)
    db_query = db_query.order_by(desc(Release.added_date))

    # Apply pagination
    db_query = db_query.offset(skip).limit(limit)

    result = await db.execute(db_query)
    return result.scalars().all()


async def create_release(db: AsyncSession, release_in: ReleaseCreate) -> Release:
    """
    Create a new release
    """
    # Check if release with GUID already exists
    existing_release = await get_release_by_guid(db, guid=release_in.guid)
    if existing_release:
        raise ValueError("Release with this GUID already exists")

    # Create new release
    db_release = Release(
        name=release_in.name,
        search_name=release_in.search_name,
        guid=release_in.guid,
        category_id=release_in.category_id,
        group_id=release_in.group_id,
        status=release_in.status or 1,  # Default to active
        size=0,  # Will be updated later
        files=0,  # Will be updated later
        completion=0.0,  # Will be updated later
        added_date=datetime.utcnow(),
        posted_date=None,  # Will be updated later
        passworded=0,  # Default to not passworded
        processed=False,  # Default to not processed

        # Media information
        imdb_id=release_in.imdb_id,
        tvdb_id=release_in.tvdb_id,
        tvmaze_id=release_in.tvmaze_id,
        tmdb_id=release_in.tmdb_id,
        video_codec=release_in.video_codec,
        audio_codec=release_in.audio_codec,
        resolution=release_in.resolution,

        # TV specific fields
        season=release_in.season,
        episode=release_in.episode,

        # Movie specific fields
        year=release_in.year,

        # Music specific fields
        artist=release_in.artist,
        album=release_in.album,

        # Release description and details
        description=release_in.description,
        details_link=release_in.details_link,
    )
    db.add(db_release)
    await db.commit()
    await db.refresh(db_release)
    return db_release


async def update_release(
    db: AsyncSession, release_id: int, release_in: ReleaseUpdate
) -> Optional[Release]:
    """
    Update a release
    """
    db_release = await get_release(db, release_id)
    if not db_release:
        return None

    # Update release fields
    update_data = release_in.dict(exclude_unset=True)

    # Update release object
    for field, value in update_data.items():
        setattr(db_release, field, value)

    db_release.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(db_release)
    return db_release


async def delete_release(db: AsyncSession, release_id: int) -> Optional[Release]:
    """
    Delete a release
    """
    db_release = await get_release(db, release_id)
    if not db_release:
        return None

    await db.delete(db_release)
    await db.commit()
    return db_release


async def update_release_stats(
    db: AsyncSession,
    release_id: int,
    size: Optional[int] = None,
    files: Optional[int] = None,
    completion: Optional[float] = None,
    posted_date: Optional[datetime] = None,
    passworded: Optional[int] = None,
    processed: Optional[bool] = None
) -> Optional[Release]:
    """
    Update release statistics
    """
    db_release = await get_release(db, release_id)
    if not db_release:
        return None

    if size is not None:
        db_release.size = size

    if files is not None:
        db_release.files = files

    if completion is not None:
        db_release.completion = completion

    if posted_date is not None:
        db_release.posted_date = posted_date

    if passworded is not None:
        db_release.passworded = passworded

    if processed is not None:
        db_release.processed = processed

    db_release.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(db_release)
    return db_release


async def increment_grab_count(
    db: AsyncSession, release_id: int, user_id: int
) -> Optional[Release]:
    """
    Increment the grab count for a release and update user's grab count
    """
    from app.services.user import increment_user_grabs

    db_release = await get_release(db, release_id)
    if not db_release:
        return None

    # Increment release grab count
    db_release.grabs += 1
    db_release.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(db_release)

    # Increment user grab count
    await increment_user_grabs(db, user_id)

    return db_release


async def get_release_count(
    db: AsyncSession,
    category_id: Optional[int] = None,
    group_id: Optional[int] = None,
    status: Optional[int] = None
) -> int:
    """
    Get the total count of releases with optional filtering
    """
    query = select(func.count(Release.id))

    # Apply filters if provided
    filters = []
    if category_id is not None:
        filters.append(Release.category_id == category_id)

    if group_id is not None:
        filters.append(Release.group_id == group_id)

    if status is not None:
        filters.append(Release.status == status)

    if filters:
        query = query.filter(and_(*filters))

    result = await db.execute(query)
    return result.scalar_one()


async def get_latest_releases(
    db: AsyncSession, limit: int = 10, category_id: Optional[int] = None
) -> List[Release]:
    """
    Get the latest releases with optional category filtering
    """
    query = select(Release).filter(Release.status == 1)  # Active releases only

    if category_id is not None:
        query = query.filter(Release.category_id == category_id)

    query = query.order_by(desc(Release.added_date)).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()
