"""
Database initialization script for NZB Indexer
Version: 0.3.0
"""

import asyncio
import logging

from app.core.config import settings

from app.db.models.base import Base
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def init_db() -> None:
    """Initialize the database with tables and initial data."""
    logger.info("Creating database tables...")

    # Create async engine
    engine = create_async_engine(settings.DATABASE_URL, echo=True)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database tables created successfully!")


async def main() -> None:
    """Main entry point for database initialization."""
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialization completed!")


if __name__ == "__main__":
    asyncio.run(main())
