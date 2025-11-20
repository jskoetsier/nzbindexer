"""
Release Regex Database Model

Stores regex patterns for matching release names from obfuscated subjects.
Based on NNTmux's proven approach with 1000+ patterns.
"""

from datetime import datetime, timezone
from typing import Optional

from app.db.models.base import Base

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class ReleaseRegex(Base):
    """
    Release regex pattern for matching obfuscated releases

    Patterns are applied in order (by ordinal) to extract clean release names
    from obfuscated Usenet subjects.
    """

    __tablename__ = "release_regexes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Group pattern (regex to match newsgroup name, or * for all groups)
    # Examples: "alt\\.binaries\\..*", "alt\\.binaries\\.teevee", "*"
    group_pattern: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Regex pattern to match subject and extract release name
    # Uses Python re module syntax with named capture groups
    # Example: r"(?P<name>.*?)\s*-\s*\[\d+\/\d+\]"
    regex: Mapped[str] = mapped_column(Text, nullable=False)

    # Description of what this regex matches
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Ordinal/priority (lower numbers = higher priority)
    # More specific patterns should have lower ordinals
    ordinal: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, index=True
    )

    # Whether this regex is active
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Statistics
    match_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<ReleaseRegex(id={self.id}, group='{self.group_pattern}', ordinal={self.ordinal}, active={self.active})>"
