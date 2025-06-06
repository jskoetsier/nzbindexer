from typing import Optional

from app.db.models.base import Base

from sqlalchemy import Boolean, Column, Integer, String, Text


class Setting(Base):
    """
    Application settings model
    """

    __allow_unmapped__ = True
    key = Column(String(255), unique=True, index=True, nullable=False)
    value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Setting {self.key}={self.value}>"
