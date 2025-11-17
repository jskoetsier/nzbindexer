import os
from typing import AsyncGenerator

from app.core.config import settings
from app.db.init_db import get_database_url

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Create async engine with connection pooling limits
engine = create_async_engine(
    get_database_url(),
    echo=False,
    future=True,
    pool_pre_ping=True,
    pool_size=20,  # Maximum number of permanent connections
    max_overflow=30,  # Maximum number of overflow connections
    pool_timeout=30,  # Timeout for getting a connection from the pool
    pool_recycle=3600,  # Recycle connections after 1 hour
)

# Create async session factory
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting async database session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
