from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.models.base import Base


class Group(Base):
    """
    Usenet newsgroup model
    """
    name = Column(String(255), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)

    # Group status
    active = Column(Boolean, default=True, nullable=False)
    backfill = Column(Boolean, default=False, nullable=False)

    # Group processing settings
    min_files = Column(Integer, default=1, nullable=False)
    min_size = Column(Integer, default=0, nullable=False)  # Minimum size in bytes

    # Group statistics
    first_article_id = Column(Integer, default=0, nullable=False)
    last_article_id = Column(Integer, default=0, nullable=False)
    current_article_id = Column(Integer, default=0, nullable=False)

    backfill_target = Column(Integer, default=0, nullable=False)

    # Group processing timestamps
    last_updated = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_article_date = Column(DateTime, nullable=True)

    # Relationships
    # articles = relationship("Article", back_populates="group")
    # releases = relationship("Release", back_populates="group")

    def __repr__(self) -> str:
        return f"<Group {self.name}>"
