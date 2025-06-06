from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class GroupBase(BaseModel):
    """
    Base group schema with common fields
    """
    name: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = True
    backfill: Optional[bool] = False
    min_files: Optional[int] = 1
    min_size: Optional[int] = 0


class GroupCreate(GroupBase):
    """
    Group creation schema
    """
    name: str


class GroupUpdate(GroupBase):
    """
    Group update schema
    """
    pass


class GroupResponse(GroupBase):
    """
    Group response schema
    """
    id: int
    name: str
    active: bool
    backfill: bool
    first_article_id: int
    last_article_id: int
    current_article_id: int
    backfill_target: int
    last_updated: datetime
    last_article_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
