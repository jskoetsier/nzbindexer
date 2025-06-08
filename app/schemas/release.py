"""
Release schemas for API requests and responses
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ReleaseBase(BaseModel):
    """
    Base schema for Release
    """

    name: str
    search_name: str
    guid: str
    size: int = 0
    files: int = 0
    completion: float = 0.0
    status: int = 1  # 1=active, 0=inactive
    passworded: int = 0  # 0=no, 1=yes, 2=unknown
    category_id: int
    group_id: int


class ReleaseCreate(ReleaseBase):
    """
    Schema for creating a new Release
    """

    posted_date: Optional[datetime] = None
    description: Optional[str] = None
    nzb_guid: Optional[str] = None


class ReleaseUpdate(BaseModel):
    """
    Schema for updating an existing Release
    """

    name: Optional[str] = None
    search_name: Optional[str] = None
    size: Optional[int] = None
    files: Optional[int] = None
    completion: Optional[float] = None
    status: Optional[int] = None
    passworded: Optional[int] = None
    category_id: Optional[int] = None
    group_id: Optional[int] = None
    posted_date: Optional[datetime] = None
    description: Optional[str] = None
    nzb_guid: Optional[str] = None
    processed: Optional[bool] = None

    # Media information
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    resolution: Optional[str] = None

    # TV specific fields
    season: Optional[str] = None
    episode: Optional[str] = None

    # Movie specific fields
    year: Optional[int] = None

    # Music specific fields
    artist: Optional[str] = None
    album: Optional[str] = None

    # External IDs
    imdb_id: Optional[str] = None
    tvdb_id: Optional[int] = None
    tvmaze_id: Optional[int] = None
    tmdb_id: Optional[int] = None


class ReleaseInDB(ReleaseBase):
    """
    Schema for Release in database
    """

    id: int
    added_date: datetime
    posted_date: Optional[datetime] = None
    processed: bool = False

    # Media information
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    resolution: Optional[str] = None

    # TV specific fields
    season: Optional[str] = None
    episode: Optional[str] = None

    # Movie specific fields
    year: Optional[int] = None

    # Music specific fields
    artist: Optional[str] = None
    album: Optional[str] = None

    # External IDs
    imdb_id: Optional[str] = None
    tvdb_id: Optional[int] = None
    tvmaze_id: Optional[int] = None
    tmdb_id: Optional[int] = None

    # Release statistics
    grabs: int = 0
    comments: int = 0

    # Release description and details
    description: Optional[str] = None
    details_link: Optional[str] = None

    # Cover and sample images
    cover: Optional[str] = None
    cover_title: Optional[str] = None

    # NZB information
    nzb_guid: Optional[str] = None

    class Config:
        orm_mode = True


class Release(ReleaseInDB):
    """
    Schema for Release API response
    """

    pass


class ReleaseWithCategory(Release):
    """
    Schema for Release with Category information
    """

    from app.schemas.category import CategoryResponse

    category: CategoryResponse


class ReleaseWithGroup(Release):
    """
    Schema for Release with Group information
    """

    from app.schemas.group import GroupResponse

    group: GroupResponse


class ReleaseWithDetails(ReleaseWithCategory, ReleaseWithGroup):
    """
    Schema for Release with all details
    """

    pass


class ReleaseSearchParams(BaseModel):
    """
    Schema for Release search parameters
    """

    search: Optional[str] = None
    category_id: Optional[int] = None
    group_id: Optional[int] = None
    sort_by: str = "added_date"
    sort_desc: bool = True
    skip: int = 0
    limit: int = 100


class ReleaseList(BaseModel):
    """
    Schema for paginated list of Releases
    """

    items: List[Release]
    total: int
