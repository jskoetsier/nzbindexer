"""
ORN (Obfuscated Release Names) Mapping Model

Stores mappings between obfuscated hashes/names and real release names.
"""

from datetime import datetime, timezone

from app.db.models.base import Base
from sqlalchemy import Column, DateTime, Float, Index, Integer, String


class ORNMapping(Base):
    """
    ORN (Obfuscated Release Names) Mapping

    Stores verified mappings between obfuscated hashes and real release names.
    Used to cache PreDB lookups and manual mappings.
    """

    __tablename__ = "orn_mappings"

    id = Column(Integer, primary_key=True, index=True)
    obfuscated_hash = Column(String(500), unique=True, index=True, nullable=False)
    real_name = Column(String(500), nullable=False, index=True)
    source = Column(String(50), nullable=False)  # predb, manual, newznab, etc.
    confidence = Column(Float, nullable=False, default=1.0)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_used = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    use_count = Column(Integer, default=1)

    # Indexes for performance
    __table_args__ = (
        Index("idx_orn_obfuscated", "obfuscated_hash"),
        Index("idx_orn_real_name", "real_name"),
        Index("idx_orn_source", "source"),
    )

    def __repr__(self):
        return f"<ORNMapping(obfuscated='{self.obfuscated_hash}', real='{self.real_name}', source='{self.source}')>"
