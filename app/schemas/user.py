from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, validator


class UserBase(BaseModel):
    """
    Base user schema with common fields
    """
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    is_active: Optional[bool] = True
    is_admin: Optional[bool] = False
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    theme: Optional[str] = "default"
    items_per_page: Optional[int] = 50


class UserCreate(UserBase):
    """
    User creation schema
    """
    email: EmailStr
    username: str
    password: str

    @validator("username")
    def username_alphanumeric(cls, v):
        if not v.isalnum():
            raise ValueError("Username must be alphanumeric")
        return v


class UserUpdate(UserBase):
    """
    User update schema
    """
    password: Optional[str] = None


class UserResponse(UserBase):
    """
    User response schema
    """
    id: int
    email: EmailStr
    username: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    updated_at: datetime
    grabs: int = 0
    last_login: Optional[datetime] = None
    last_browse: Optional[datetime] = None

    class Config:
        orm_mode = True
