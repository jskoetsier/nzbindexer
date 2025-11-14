from datetime import datetime, timezone
from typing import Optional

from app.db.models.base import Base

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship


def _utc_now():
    """Helper function to get timezone-aware UTC datetime"""
    return datetime.now(timezone.utc)


class User(Base):
    """
    User model for authentication and user management
    """

    __allow_unmapped__ = True
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)

    # User status
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_confirmed = Column(Boolean, default=False, nullable=False)

    # User details
    first_name = Column(String(50), nullable=True)
    last_name = Column(String(50), nullable=True)

    # API access
    api_key = Column(String(32), unique=True, index=True, nullable=True)
    api_requests = Column(Integer, default=0, nullable=False)
    api_requests_today = Column(Integer, default=0, nullable=False)
    api_requests_reset = Column(DateTime(timezone=True), default=_utc_now, nullable=False)

    # User preferences
    theme = Column(String(50), default="default", nullable=False)
    items_per_page = Column(Integer, default=50, nullable=False)

    # User statistics
    grabs = Column(Integer, default=0, nullable=False)
    last_login = Column(DateTime(timezone=True), nullable=True)
    last_browse = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    # releases = relationship("Release", back_populates="user")
    # comments = relationship("Comment", back_populates="user")
    # downloads = relationship("Download", back_populates="user")

    def __repr__(self) -> str:
        return f"<User {self.username}>"
