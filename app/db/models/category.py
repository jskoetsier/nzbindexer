from app.db.models.base import Base
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship


class Category(Base):
    """
    Category model for organizing releases
    """

    __allow_unmapped__ = True
    name = Column(String(64), unique=True, nullable=False)
    description = Column(Text, nullable=True)

    # Category hierarchy
    parent_id = Column(Integer, ForeignKey("category.id"), nullable=True)
    children = relationship(
        "Category", backref="parent", remote_side=[id], cascade="all, delete-orphan"
    )

    # Category status
    active = Column(Boolean, default=True, nullable=False)

    # Category display settings
    icon = Column(String(255), nullable=True)
    color = Column(String(7), nullable=True)  # Hex color code

    # Category sorting
    sort_order = Column(Integer, default=0, nullable=False)

    # Disqus settings
    disqus_identifier = Column(String(64), nullable=True)

    # Relationships
    # releases = relationship("Release", back_populates="category")

    def __repr__(self) -> str:
        return f"<Category {self.name}>"
