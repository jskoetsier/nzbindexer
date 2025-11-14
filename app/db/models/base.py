from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.ext.declarative import as_declarative, declared_attr


def _utc_now():
    """Helper function to get timezone-aware UTC datetime"""
    return datetime.now(timezone.utc)


@as_declarative()
class Base:
    """
    Base class for all SQLAlchemy models
    """

    __allow_unmapped__ = True
    __name__: str

    # Generate __tablename__ automatically based on class name
    @declared_attr
    def __tablename__(cls) -> str:
        return cls.__name__.lower()

    # Common columns for all models - use timezone=True for PostgreSQL TIMESTAMP WITH TIME ZONE
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )
