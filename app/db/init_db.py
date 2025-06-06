"""
Database initialization script for NZB Indexer
Version: 0.3.0
"""

import asyncio
import logging
import os
from typing import Optional

from app.core.config import settings
from app.db.models.base import Base
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def init_db() -> None:
    """Initialize the database with tables and initial data."""
    logger.info("Creating database tables...")

    # Determine database URL
    db_url = get_database_url()
    logger.info(f"Using database URL: {db_url}")

    # Create async engine
    engine = create_async_engine(db_url, echo=True)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database tables created successfully!")


def get_database_url() -> str:
    """
    Get the database URL from settings or environment variables.
    Falls back to SQLite if no PostgreSQL configuration is found.
    """
    # Check if SQLALCHEMY_DATABASE_URI is set in settings
    if settings.SQLALCHEMY_DATABASE_URI:
        return str(settings.SQLALCHEMY_DATABASE_URI)

    # Check for environment variable
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        # Handle Heroku-style postgres:// URLs
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        return db_url

    # Fall back to SQLite
    logger.info("No PostgreSQL configuration found, using SQLite")
    db_path = os.path.join(os.getcwd(), "app.db")
    return f"sqlite+aiosqlite:///{db_path}"


async def main() -> None:
    """Main entry point for database initialization."""
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialization completed!")


if __name__ == "__main__":
    asyncio.run(main())
