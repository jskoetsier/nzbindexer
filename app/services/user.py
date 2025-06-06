from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.db.models.user import User
from app.schemas.user import UserCreate, UserUpdate


async def get_user(db: AsyncSession, user_id: int) -> Optional[User]:
    """
    Get a user by ID
    """
    result = await db.execute(select(User).filter(User.id == user_id))
    return result.scalars().first()


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """
    Get a user by email
    """
    result = await db.execute(select(User).filter(User.email == email))
    return result.scalars().first()


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    """
    Get a user by username
    """
    result = await db.execute(select(User).filter(User.username == username))
    return result.scalars().first()


async def get_users(
    db: AsyncSession, skip: int = 0, limit: int = 100
) -> List[User]:
    """
    Get multiple users with pagination
    """
    result = await db.execute(select(User).offset(skip).limit(limit))
    return result.scalars().all()


async def create_user(db: AsyncSession, user_in: UserCreate) -> User:
    """
    Create a new user
    """
    # Check if user with email already exists
    existing_user = await get_user_by_email(db, email=user_in.email)
    if existing_user:
        raise ValueError("User with this email already exists")

    # Check if user with username already exists
    existing_user = await get_user_by_username(db, username=user_in.username)
    if existing_user:
        raise ValueError("User with this username already exists")

    # Create new user
    db_user = User(
        email=user_in.email,
        username=user_in.username,
        hashed_password=get_password_hash(user_in.password),
        is_active=user_in.is_active,
        is_admin=user_in.is_admin,
        first_name=user_in.first_name,
        last_name=user_in.last_name,
        theme=user_in.theme,
        items_per_page=user_in.items_per_page,
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user


async def update_user(
    db: AsyncSession, user_id: int, user_in: UserUpdate
) -> Optional[User]:
    """
    Update a user
    """
    db_user = await get_user(db, user_id)
    if not db_user:
        return None

    # Update user fields
    update_data = user_in.dict(exclude_unset=True)

    # Hash password if provided
    if "password" in update_data and update_data["password"]:
        update_data["hashed_password"] = get_password_hash(update_data["password"])
        del update_data["password"]

    # Update user object
    for field, value in update_data.items():
        setattr(db_user, field, value)

    db_user.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(db_user)
    return db_user


async def delete_user(db: AsyncSession, user_id: int) -> Optional[User]:
    """
    Delete a user
    """
    db_user = await get_user(db, user_id)
    if not db_user:
        return None

    await db.delete(db_user)
    await db.commit()
    return db_user


async def update_user_login(db: AsyncSession, user_id: int) -> Optional[User]:
    """
    Update user's last login timestamp
    """
    db_user = await get_user(db, user_id)
    if not db_user:
        return None

    db_user.last_login = datetime.utcnow()
    await db.commit()
    await db.refresh(db_user)
    return db_user


async def update_user_browse(db: AsyncSession, user_id: int) -> Optional[User]:
    """
    Update user's last browse timestamp
    """
    db_user = await get_user(db, user_id)
    if not db_user:
        return None

    db_user.last_browse = datetime.utcnow()
    await db.commit()
    await db.refresh(db_user)
    return db_user


async def increment_user_grabs(db: AsyncSession, user_id: int) -> Optional[User]:
    """
    Increment user's grab count
    """
    db_user = await get_user(db, user_id)
    if not db_user:
        return None

    db_user.grabs += 1
    await db.commit()
    await db.refresh(db_user)
    return db_user
