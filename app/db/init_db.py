"""
Database initialization script for NZB Indexer
Version: 0.5.4
"""

import asyncio
import logging
import os
from typing import Optional

from app.core.config import settings
from app.db.models.base import Base
from sqlalchemy import text
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

    # Initialize settings
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        await init_settings(session)
        await init_categories(session)


async def init_settings(db: AsyncSession) -> None:
    """
    Initialize settings with default values
    """
    logger.info("Initializing settings...")

    try:
        # Check if settings table exists and has data
        try:
            query = text("SELECT COUNT(*) FROM setting")
            result = await db.execute(query)
            count = result.scalar()
        except Exception:
            # Table might not exist yet
            count = 0

        if count == 0:
            logger.info("Creating default settings...")

            # Import here to avoid circular imports
            from app.schemas.setting import AppSettings
            from app.services.setting import update_app_settings

            # Create default settings
            default_settings = AppSettings(
                allow_registration=True,
                nntp_server=settings.NNTP_SERVER,
                nntp_port=settings.NNTP_PORT,
                nntp_ssl=settings.NNTP_SSL,
                nntp_ssl_port=settings.NNTP_SSL_PORT,
                nntp_username=settings.NNTP_USERNAME,
                nntp_password=settings.NNTP_PASSWORD,
                update_threads=settings.UPDATE_THREADS,
                releases_threads=settings.RELEASES_THREADS,
                postprocess_threads=settings.POSTPROCESS_THREADS,
                backfill_days=settings.BACKFILL_DAYS,
                retention_days=settings.RETENTION_DAYS,
            )

            # Save settings to database
            await update_app_settings(db, default_settings)

            logger.info("Default settings created successfully!")
        else:
            logger.info("Settings already exist, skipping initialization.")

    except Exception as e:
        logger.error(f"Error initializing settings: {str(e)}")
        # Don't raise the exception, just log it
        # This allows the database initialization to continue even if settings initialization fails


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
        # Handle Heroku-style postgres:// URLs and ensure asyncpg driver
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif not db_url.startswith("postgresql+asyncpg://") and not db_url.startswith(
            "sqlite"
        ):
            # If it's a postgresql URL but doesn't specify the driver, add asyncpg
            if "postgresql" in db_url:
                db_url = db_url.replace("postgresql", "postgresql+asyncpg", 1)
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


async def init_categories(db: AsyncSession) -> None:
    """
    Initialize Newznab standard categories for TV and Movies
    """
    logger.info("Initializing categories...")
    
    try:
        from app.db.models.category import Category
        from sqlalchemy import select
        
        # Check if categories already exist
        query = select(Category)
        result = await db.execute(query)
        existing_categories = result.scalars().all()
        
        if len(existing_categories) > 0:
            logger.info(f"Categories already exist ({len(existing_categories)} found), skipping initialization.")
            return
        
        logger.info("Creating Newznab standard categories...")
        
        # Newznab Standard Categories
        # https://github.com/nZEDb/nZEDb/blob/0.x/docs/newznab_api_specification.txt
        
        categories_data = [
            # Movies (2000-2999)
            {"name": "Movies", "newznab_category": 2000, "parent_id": None, "sort_order": 1, "description": "Movies"},
            {"name": "Movies/Foreign", "newznab_category": 2010, "parent_name": "Movies", "sort_order": 2, "description": "Foreign Movies"},
            {"name": "Movies/Other", "newznab_category": 2020, "parent_name": "Movies", "sort_order": 3, "description": "Other Movies"},
            {"name": "Movies/SD", "newznab_category": 2030, "parent_name": "Movies", "sort_order": 4, "description": "Standard Definition Movies"},
            {"name": "Movies/HD", "newznab_category": 2040, "parent_name": "Movies", "sort_order": 5, "description": "High Definition Movies"},
            {"name": "Movies/UHD", "newznab_category": 2045, "parent_name": "Movies", "sort_order": 6, "description": "Ultra HD Movies (4K)"},
            {"name": "Movies/BluRay", "newznab_category": 2050, "parent_name": "Movies", "sort_order": 7, "description": "Blu-ray Movies"},
            {"name": "Movies/3D", "newznab_category": 2060, "parent_name": "Movies", "sort_order": 8, "description": "3D Movies"},
            
            # TV (5000-5999)
            {"name": "TV", "newznab_category": 5000, "parent_id": None, "sort_order": 10, "description": "TV Shows"},
            {"name": "TV/Foreign", "newznab_category": 5020, "parent_name": "TV", "sort_order": 11, "description": "Foreign TV Shows"},
            {"name": "TV/SD", "newznab_category": 5030, "parent_name": "TV", "sort_order": 12, "description": "Standard Definition TV Shows"},
            {"name": "TV/HD", "newznab_category": 5040, "parent_name": "TV", "sort_order": 13, "description": "High Definition TV Shows"},
            {"name": "TV/UHD", "newznab_category": 5045, "parent_name": "TV", "sort_order": 14, "description": "Ultra HD TV Shows (4K)"},
            {"name": "TV/Other", "newznab_category": 5050, "parent_name": "TV", "sort_order": 15, "description": "Other TV Shows"},
            {"name": "TV/Sport", "newznab_category": 5060, "parent_name": "TV", "sort_order": 16, "description": "Sports TV"},
            {"name": "TV/Anime", "newznab_category": 5070, "parent_name": "TV", "sort_order": 17, "description": "Anime TV Shows"},
            {"name": "TV/Documentary", "newznab_category": 5080, "parent_name": "TV", "sort_order": 18, "description": "TV Documentaries"},
            
            # Music (3000-3999)
            {"name": "Audio", "newznab_category": 3000, "parent_id": None, "sort_order": 20, "description": "Audio/Music"},
            {"name": "Audio/MP3", "newznab_category": 3010, "parent_name": "Audio", "sort_order": 21, "description": "MP3 Music"},
            {"name": "Audio/Video", "newznab_category": 3020, "parent_name": "Audio", "sort_order": 22, "description": "Music Videos"},
            {"name": "Audio/Audiobook", "newznab_category": 3030, "parent_name": "Audio", "sort_order": 23, "description": "Audio Books"},
            {"name": "Audio/Lossless", "newznab_category": 3040, "parent_name": "Audio", "sort_order": 24, "description": "Lossless Music"},
            {"name": "Audio/Other", "newznab_category": 3050, "parent_name": "Audio", "sort_order": 25, "description": "Other Audio"},
            {"name": "Audio/Foreign", "newznab_category": 3060, "parent_name": "Audio", "sort_order": 26, "description": "Foreign Audio"},
            
            # PC (4000-4999)
            {"name": "PC", "newznab_category": 4000, "parent_id": None, "sort_order": 30, "description": "PC Software & Games"},
            {"name": "PC/0day", "newznab_category": 4010, "parent_name": "PC", "sort_order": 31, "description": "PC 0-day Software"},
            {"name": "PC/ISO", "newznab_category": 4020, "parent_name": "PC", "sort_order": 32, "description": "PC ISO"},
            {"name": "PC/Mac", "newznab_category": 4030, "parent_name": "PC", "sort_order": 33, "description": "Mac Software"},
            {"name": "PC/Mobile-Other", "newznab_category": 4040, "parent_name": "PC", "sort_order": 34, "description": "Mobile Apps"},
            {"name": "PC/Games", "newznab_category": 4050, "parent_name": "PC", "sort_order": 35, "description": "PC Games"},
            {"name": "PC/Mobile-iOS", "newznab_category": 4060, "parent_name": "PC", "sort_order": 36, "description": "iOS Apps"},
            {"name": "PC/Mobile-Android", "newznab_category": 4070, "parent_name": "PC", "sort_order": 37, "description": "Android Apps"},
            
            # Console (1000-1999)
            {"name": "Console", "newznab_category": 1000, "parent_id": None, "sort_order": 40, "description": "Console Games"},
            {"name": "Console/NDS", "newznab_category": 1010, "parent_name": "Console", "sort_order": 41, "description": "Nintendo DS Games"},
            {"name": "Console/PSP", "newznab_category": 1020, "parent_name": "Console", "sort_order": 42, "description": "Sony PSP Games"},
            {"name": "Console/Wii", "newznab_category": 1030, "parent_name": "Console", "sort_order": 43, "description": "Nintendo Wii Games"},
            {"name": "Console/Xbox", "newznab_category": 1040, "parent_name": "Console", "sort_order": 44, "description": "Xbox Games"},
            {"name": "Console/Xbox 360", "newznab_category": 1050, "parent_name": "Console", "sort_order": 45, "description": "Xbox 360 Games"},
            {"name": "Console/Wii U", "newznab_category": 1060, "parent_name": "Console", "sort_order": 46, "description": "Wii U Games"},
            {"name": "Console/Xbox One", "newznab_category": 1070, "parent_name": "Console", "sort_order": 47, "description": "Xbox One Games"},
            {"name": "Console/PS3", "newznab_category": 1080, "parent_name": "Console", "sort_order": 48, "description": "PlayStation 3 Games"},
            {"name": "Console/PS4", "newznab_category": 1110, "parent_name": "Console", "sort_order": 49, "description": "PlayStation 4 Games"},
            {"name": "Console/PS5", "newznab_category": 1180, "parent_name": "Console", "sort_order": 50, "description": "PlayStation 5 Games"},
            {"name": "Console/Switch", "newznab_category": 1140, "parent_name": "Console", "sort_order": 51, "description": "Nintendo Switch Games"},
            
            # Books (7000-7999) & Other (8000-8999)
            {"name": "Books", "newznab_category": 7000, "parent_id": None, "sort_order": 60, "description": "Books & Ebooks"},
            {"name": "Books/Ebook", "newznab_category": 7020, "parent_name": "Books", "sort_order": 61, "description": "Ebooks"},
            {"name": "Books/Comics", "newznab_category": 7030, "parent_name": "Books", "sort_order": 62, "description": "Comics"},
            
            {"name": "Other", "newznab_category": 8000, "parent_id": None, "sort_order": 70, "description": "Other/Misc"},
            {"name": "Other/Misc", "newznab_category": 8010, "parent_name": "Other", "sort_order": 71, "description": "Miscellaneous"},
        ]
        
        # Create parent categories first, then children
        parent_categories = {}
        
        # First pass: Create parent categories
        for cat_data in categories_data:
            if cat_data.get("parent_id") is None and "parent_name" not in cat_data:
                category = Category(
                    name=cat_data["name"],
                    newznab_category=cat_data["newznab_category"],
                    parent_id=None,
                    sort_order=cat_data["sort_order"],
                    description=cat_data.get("description"),
                    active=True
                )
                db.add(category)
                await db.flush()  # Flush to get the ID
                parent_categories[cat_data["name"]] = category.id
                logger.info(f"Created parent category: {cat_data['name']} (ID: {category.id}, Newznab: {cat_data['newznab_category']})")
        
        # Second pass: Create child categories
        for cat_data in categories_data:
            if "parent_name" in cat_data:
                parent_id = parent_categories.get(cat_data["parent_name"])
                if parent_id:
                    category = Category(
                        name=cat_data["name"],
                        newznab_category=cat_data["newznab_category"],
                        parent_id=parent_id,
                        sort_order=cat_data["sort_order"],
                        description=cat_data.get("description"),
                        active=True
                    )
                    db.add(category)
                    logger.info(f"Created child category: {cat_data['name']} (Parent: {cat_data['parent_name']}, Newznab: {cat_data['newznab_category']})")
        
        await db.commit()
        logger.info(f"Successfully created {len(categories_data)} Newznab standard categories!")
        
    except Exception as e:
        logger.error(f"Error initializing categories: {str(e)}")
        await db.rollback()
        # Don't raise - allow initialization to continue


async def main() -> None:
    """Main entry point for database initialization."""
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialization completed!")


if __name__ == "__main__":
    asyncio.run(main())
