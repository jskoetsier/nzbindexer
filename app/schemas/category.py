from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class CategoryBase(BaseModel):
    """
    Base category schema with common fields
    """

    name: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = True
    icon: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = 0
    parent_id: Optional[int] = None
    newznab_category: Optional[int] = None  # Newznab/Sonarr category ID


class CategoryCreate(CategoryBase):
    """
    Category creation schema
    """

    name: str


class CategoryUpdate(CategoryBase):
    """
    Category update schema
    """

    pass


class CategoryResponse(CategoryBase):
    """
    Category response schema
    """

    id: int
    name: str
    active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class CategoryWithChildren(CategoryResponse):
    """
    Category response schema with children
    """

    children: List["CategoryWithChildren"] = []

    class Config:
        orm_mode = True


# This is needed for the self-referencing model
CategoryWithChildren.update_forward_refs()
