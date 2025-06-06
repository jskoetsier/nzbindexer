from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, BigInteger
)
from sqlalchemy.orm import relationship

from app.db.models.base import Base


class Release(Base):
    """
    Release model representing a complete Usenet release
    """
    # Basic release information
    name = Column(String(255), index=True, nullable=False)
    search_name = Column(String(255), index=True, nullable=False)
    guid = Column(String(50), unique=True, index=True, nullable=False)

    # Release details
    size = Column(BigInteger, default=0, nullable=False)  # Size in bytes
    files = Column(Integer, default=0, nullable=False)
    completion = Column(Float, default=0, nullable=False)  # Percentage complete

    # Release dates
    posted_date = Column(DateTime, nullable=True, index=True)
    added_date = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Release status
    status = Column(Integer, default=1, nullable=False)  # 1=active, 0=inactive, etc.
    passworded = Column(Integer, default=0, nullable=False)  # 0=no, 1=yes, 2=unknown

    # Release categorization
    category_id = Column(Integer, ForeignKey("category.id"), nullable=False)
    category = relationship("Category", backref="releases")

    group_id = Column(Integer, ForeignKey("group.id"), nullable=False)
    group = relationship("Group", backref="releases")

    # Release content information
    imdb_id = Column(String(10), nullable=True)
    tvdb_id = Column(Integer, nullable=True)
    tvmaze_id = Column(Integer, nullable=True)
    tmdb_id = Column(Integer, nullable=True)

    # Media information
    video_codec = Column(String(50), nullable=True)
    audio_codec = Column(String(50), nullable=True)
    resolution = Column(String(50), nullable=True)

    # TV specific fields
    season = Column(String(10), nullable=True)
    episode = Column(String(10), nullable=True)

    # Movie specific fields
    year = Column(Integer, nullable=True)

    # Music specific fields
    artist = Column(String(255), nullable=True)
    album = Column(String(255), nullable=True)

    # Release statistics
    grabs = Column(Integer, default=0, nullable=False)
    comments = Column(Integer, default=0, nullable=False)

    # Release processing
    processed = Column(Boolean, default=False, nullable=False)
    nzb_guid = Column(String(32), nullable=True)

    # Release description and details
    description = Column(Text, nullable=True)
    details_link = Column(String(255), nullable=True)

    # Cover and sample images
    cover = Column(String(255), nullable=True)
    cover_title = Column(String(255), nullable=True)

    # Relationships
    # nzb = relationship("NZB", back_populates="release", uselist=False)
    # comments = relationship("Comment", back_populates="release")
    # downloads = relationship("Download", back_populates="release")

    def __repr__(self) -> str:
        return f"<Release {self.name}>"
