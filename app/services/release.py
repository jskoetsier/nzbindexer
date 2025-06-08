"""
Release service for managing Usenet releases
"""

import hashlib
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Union

from app.core.config import settings
from app.db.models.release import Release
from app.db.session import AsyncSession
from app.schemas.release import ReleaseCreate, ReleaseUpdate

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def create_release_guid(name: str, group_name: str) -> str:
    """
    Create a unique GUID for a release based on its name and group
    """
    # Create a unique string from name and group
    unique_str = f"{name}:{group_name}"

    # Create MD5 hash
    md5 = hashlib.md5(unique_str.encode()).hexdigest()

    return md5


async def create_release(db: AsyncSession, release_in: ReleaseCreate) -> Release:
    """
    Create a new release
    """
    # Create release object
    release = Release(
        name=release_in.name,
        search_name=release_in.search_name,
        guid=release_in.guid,
        size=release_in.size,
        files=release_in.files,
        completion=release_in.completion,
        posted_date=release_in.posted_date or datetime.utcnow(),
        added_date=datetime.utcnow(),
        status=release_in.status,
        passworded=release_in.passworded,
        category_id=release_in.category_id,
        group_id=release_in.group_id,
        processed=False,
    )

    # Add optional fields if provided
    if release_in.description:
        release.description = release_in.description

    if release_in.nzb_guid:
        release.nzb_guid = release_in.nzb_guid

    # Add to database
    db.add(release)
    await db.commit()
    await db.refresh(release)

    return release


async def update_release(
    db: AsyncSession, release_id: int, release_in: ReleaseUpdate
) -> Optional[Release]:
    """
    Update an existing release
    """
    # Get release
    query = select(Release).filter(Release.id == release_id)
    result = await db.execute(query)
    release = result.scalars().first()

    if not release:
        return None

    # Update fields
    update_data = release_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(release, field, value)

    # Save changes
    db.add(release)
    await db.commit()
    await db.refresh(release)

    return release


async def get_release(db: AsyncSession, release_id: int) -> Optional[Release]:
    """
    Get a release by ID
    """
    query = select(Release).filter(Release.id == release_id)
    result = await db.execute(query)
    return result.scalars().first()


async def get_release_by_guid(db: AsyncSession, guid: str) -> Optional[Release]:
    """
    Get a release by GUID
    """
    query = select(Release).filter(Release.guid == guid)
    result = await db.execute(query)
    return result.scalars().first()


async def get_releases(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    group_id: Optional[int] = None,
    sort_by: str = "added_date",
    sort_desc: bool = True,
) -> Dict[str, Union[List[Release], int]]:
    """
    Get releases with filtering and pagination
    """
    # Base query
    query = select(Release).filter(Release.status == 1)  # Only active releases

    # Apply filters
    if search:
        search_terms = search.split()
        for term in search_terms:
            query = query.filter(
                or_(
                    Release.name.ilike(f"%{term}%"),
                    Release.search_name.ilike(f"%{term}%"),
                )
            )

    if category_id:
        query = query.filter(Release.category_id == category_id)

    if group_id:
        query = query.filter(Release.group_id == group_id)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.execute(count_query)
    total_count = total.scalar()

    # Apply sorting
    if sort_by:
        sort_column = getattr(Release, sort_by, Release.added_date)
        if sort_desc:
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

    # Apply pagination
    query = query.offset(skip).limit(limit)

    # Execute query
    result = await db.execute(query)
    releases = result.scalars().all()

    return {
        "items": releases,
        "total": total_count,
    }


async def delete_release(db: AsyncSession, release_id: int) -> bool:
    """
    Delete a release
    """
    query = select(Release).filter(Release.id == release_id)
    result = await db.execute(query)
    release = result.scalars().first()

    if not release:
        return False

    await db.delete(release)
    await db.commit()

    return True


async def process_release(db: AsyncSession, release_id: int) -> Optional[Release]:
    """
    Process a release to extract metadata and categorize it
    """
    # Get release
    query = select(Release).filter(Release.id == release_id)
    result = await db.execute(query)
    release = result.scalars().first()

    if not release:
        return None

    try:
        # Extract metadata from release name
        metadata = extract_release_metadata(release.name)

        # Update release with metadata
        for key, value in metadata.items():
            if hasattr(release, key) and value is not None:
                setattr(release, key, value)

        # Determine appropriate category
        category_id = await determine_release_category(db, release.name, metadata)
        if category_id:
            release.category_id = category_id

        # Mark as processed
        release.processed = True

        # Save changes
        db.add(release)
        await db.commit()
        await db.refresh(release)

        return release

    except Exception as e:
        logger.error(f"Error processing release {release.id}: {str(e)}")
        return None


def extract_release_metadata(name: str) -> Dict[str, any]:
    """
    Extract metadata from a release name
    """
    metadata = {}

    # Extract year
    year_match = re.search(r"(?:^|\D)(\d{4})(?:\D|$)", name)
    if year_match:
        metadata["year"] = int(year_match.group(1))

    # Extract resolution
    res_match = re.search(r"(?:^|\D)(720p|1080p|2160p|4K)(?:\D|$)", name, re.IGNORECASE)
    if res_match:
        metadata["resolution"] = res_match.group(1).lower()

    # Extract video codec
    codec_match = re.search(
        r"(?:^|\D)(x264|x265|h264|h265|xvid|divx|hevc)(?:\D|$)", name, re.IGNORECASE
    )
    if codec_match:
        metadata["video_codec"] = codec_match.group(1).lower()

    # Extract audio codec
    audio_match = re.search(
        r"(?:^|\D)(AAC|AC3|DTS|DD5\.1|FLAC)(?:\D|$)", name, re.IGNORECASE
    )
    if audio_match:
        metadata["audio_codec"] = audio_match.group(1).upper()

    # Extract TV season/episode
    tv_match = re.search(r"S(\d{1,2})E(\d{1,2})", name, re.IGNORECASE)
    if tv_match:
        metadata["season"] = tv_match.group(1).zfill(2)
        metadata["episode"] = tv_match.group(2).zfill(2)

    # Extract music artist/album
    if " - " in name:
        parts = name.split(" - ", 1)
        if len(parts) == 2:
            metadata["artist"] = parts[0].strip()
            album_part = parts[1].strip()
            # Try to remove year and other info from album name
            album_match = re.match(
                r"^(.*?)(?:\(\d{4}\)|\[\d{4}\]|[\(\[].*?[\)\]]|[0-9]{4}|FLAC|MP3|WEB|CD)",
                album_part,
            )
            if album_match:
                metadata["album"] = album_match.group(1).strip()
            else:
                metadata["album"] = album_part

    return metadata


async def determine_release_category(
    db: AsyncSession, name: str, metadata: Dict[str, any]
) -> Optional[int]:
    """
    Determine the appropriate category for a release based on its name and metadata
    """
    from app.db.models.category import Category

    # Check for TV shows
    if "season" in metadata and "episode" in metadata:
        query = select(Category).filter(Category.name == "TV")
        result = await db.execute(query)
        tv_category = result.scalars().first()
        if tv_category:
            return tv_category.id

    # Check for movies
    movie_keywords = [
        "1080p",
        "720p",
        "2160p",
        "4K",
        "BDRip",
        "BRRip",
        "DVDRip",
        "BluRay",
        "WEB-DL",
    ]
    if (
        any(keyword.lower() in name.lower() for keyword in movie_keywords)
        and "year" in metadata
    ):
        query = select(Category).filter(Category.name == "Movies")
        result = await db.execute(query)
        movie_category = result.scalars().first()
        if movie_category:
            return movie_category.id

    # Check for music
    if "artist" in metadata and "album" in metadata:
        query = select(Category).filter(Category.name == "Music")
        result = await db.execute(query)
        music_category = result.scalars().first()
        if music_category:
            return music_category.id

    # Check for software
    software_keywords = [
        "Windows",
        "MacOS",
        "Linux",
        "ISO",
        "x86",
        "x64",
        "Setup",
        "Install",
    ]
    if any(keyword.lower() in name.lower() for keyword in software_keywords):
        query = select(Category).filter(Category.name == "Software")
        result = await db.execute(query)
        software_category = result.scalars().first()
        if software_category:
            return software_category.id

    # Default to "Other" category
    query = select(Category).filter(Category.name == "Other")
    result = await db.execute(query)
    other_category = result.scalars().first()
    if other_category:
        return other_category.id

    return None
