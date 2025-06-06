from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ReleaseBase(BaseModel):
    """
    Base release schema with common fields
    """
    name: Optional[str] = None
    search_name: Optional[str] = None
    category_id: Optional[int] = None
    group_id: Optional[int] = None
    status: Optional[int] = 1  # 1=active, 0=inactive, etc.

    # Media information
    imdb_id: Optional[str] = None
    tvdb_id: Optional[int] = None
    tvmaze_id: Optional[int] = None
    tmdb_id: Optional[int] = None
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

    # Release description and details
    description: Optional[str] = None
    details_link: Optional[str] = None


class ReleaseCreate(ReleaseBase):
    """
    Release creation schema
    """
    name: str
    search_name: str
    guid: str
    category_id: int
    group_id: int


class ReleaseUpdate(ReleaseBase):
    """
    Release update schema
    """
    pass


class ReleaseResponse(ReleaseBase):
    """
    Release response schema
    """
    id: int
    name: str
    search_name: str
    guid: str
    size: int
    files: int
    completion: float
    posted_date: Optional[datetime] = None
    added_date: datetime
    status: int
    passworded: int
    category_id: int
    group_id: int
    processed: bool
    grabs: int
    comments: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class ReleaseDetail(ReleaseResponse):
    """
    Detailed release response schema with additional information
    """
    nzb_guid: Optional[str] = None
    cover: Optional[str] = None
    cover_title: Optional[str] = None

    # Relationships
    category: Optional["CategoryResponse"] = None
    group: Optional["GroupResponse"] = None

    class Config:
        orm_mode = True


# Import here to avoid circular imports
from app.schemas.category import CategoryResponse
from app.schemas.group import GroupResponse

# Update forward refs
ReleaseDetail.update_forward_refs()
