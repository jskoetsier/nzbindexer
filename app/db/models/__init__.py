# SQLAlchemy models for NZBIndexer

# Import all models to ensure they're registered with Base.metadata
from app.db.models.base import Base
from app.db.models.category import Category
from app.db.models.group import Group
from app.db.models.release import Release
from app.db.models.setting import Setting
from app.db.models.user import User

# Export models for easy import
__all__ = ["Base", "User", "Group", "Category", "Release", "Setting"]
