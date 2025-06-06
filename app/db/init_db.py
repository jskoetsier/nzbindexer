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
    Prioritizes SQLite for development and installation environments.
    """
    # Check for installation mode (presence of install.sh in current directory)
    if os.path.exists(os.path.join(os.getcwd(), "install.sh")):
        logger.info("Installation mode detected, using SQLite")
        db_path = os.path.join(os.getcwd(), "app.db")
        return f"sqlite+aiosqlite:///{db_path}"

    # Check for environment variable indicating development mode
    if os.environ.get("NZBINDEXER_ENV") == "dev" or os.environ.get(
        "NZBINDEXER_USE_SQLITE"
    ):
        logger.info("Development mode detected, using SQLite")
        db_path = os.path.join(os.getcwd(), "app.db")
        return f"sqlite+aiosqlite:///{db_path}"

    # Check for explicit DATABASE_URL environment variable
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        # Handle Heroku-style postgres:// URLs
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        logger.info(f"Using DATABASE_URL from environment: {db_url}")
        return db_url

    # Check if SQLALCHEMY_DATABASE_URI is set in settings and PostgreSQL is available
    if settings.SQLALCHEMY_DATABASE_URI:
        # Try to check if PostgreSQL is available
        try:
            import socket

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            # Extract host and port from URI if possible
            uri_str = str(settings.SQLALCHEMY_DATABASE_URI)
            host = "localhost"  # Default
            port = 5432  # Default PostgreSQL port

            # Very basic parsing - in production would use proper URI parsing
            if "@" in uri_str and ":" in uri_str.split("@")[1]:
                host_port = uri_str.split("@")[1].split("/")[0]
                if ":" in host_port:
                    host, port_str = host_port.split(":")
                    try:
                        port = int(port_str)
                    except ValueError:
                        pass

            # Try to connect to check if PostgreSQL is available
            result = s.connect_ex((host, port))
            s.close()

            if result == 0:
                logger.info(
                    f"PostgreSQL is available at {host}:{port}, using configured database"
                )
                return uri_str
            else:
                logger.warning(
                    f"PostgreSQL is not available at {host}:{port}, falling back to SQLite"
                )
        except Exception as e:
            logger.warning(
                f"Error checking PostgreSQL availability: {e}, falling back to SQLite"
            )

    # Fall back to SQLite
    logger.info("Using SQLite as fallback")
    db_path = os.path.join(os.getcwd(), "app.db")
    return f"sqlite+aiosqlite:///{db_path}"


async def main() -> None:
    """Main entry point for database initialization."""
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialization completed!")


if __name__ == "__main__":
    asyncio.run(main())
