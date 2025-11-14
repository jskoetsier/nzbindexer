from datetime import datetime, timezone
from typing import Optional

from app.db.models.setting import Setting
from app.schemas.setting import AppSettings, SettingCreate, SettingUpdate

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_setting(db: AsyncSession, setting_id: int) -> Optional[Setting]:
    """
    Get a setting by ID
    """
    result = await db.execute(select(Setting).filter(Setting.id == setting_id))
    return result.scalars().first()


async def get_setting_by_key(db: AsyncSession, key: str) -> Optional[Setting]:
    """
    Get a setting by key
    """
    result = await db.execute(select(Setting).filter(Setting.key == key))
    return result.scalars().first()


async def get_settings(
    db: AsyncSession, skip: int = 0, limit: int = 100
) -> List[Setting]:
    """
    Get multiple settings with pagination
    """
    result = await db.execute(select(Setting).offset(skip).limit(limit))
    return result.scalars().all()


async def create_setting(db: AsyncSession, setting_in: SettingCreate) -> Setting:
    """
    Create a new setting
    """
    # Check if setting with key already exists
    existing_setting = await get_setting_by_key(db, key=setting_in.key)
    if existing_setting:
        raise ValueError("Setting with this key already exists")

    # Create new setting
    db_setting = Setting(
        key=setting_in.key,
        value=setting_in.value,
        description=setting_in.description,
    )
    db_setting.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(db_setting)
    return db_setting


async def update_setting(
    db: AsyncSession, setting_id: int, setting_in: SettingUpdate
) -> Optional[Setting]:
    """
    Update a setting by ID
    """
    db_setting = await get_setting(db, setting_id)
    if not db_setting:
        return None

    # Update setting fields
    update_data = setting_in.dict(exclude_unset=True)

    # Update setting object
    for field, value in update_data.items():
        setattr(db_setting, field, value)

        db_setting.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(db_setting)
    return db_setting


async def update_setting_by_key(
    db: AsyncSession, key: str, value: str, description: Optional[str] = None
) -> Optional[Setting]:
    """
    Update a setting by key
    """
    db_setting = await get_setting_by_key(db, key=key)

    if db_setting:
        # Update existing setting
        db_setting.value = value
        if description:
            db_setting.description = description
        db_setting.updated_at = datetime.now(timezone.utc)
    else:
        # Create new setting
        db_setting = Setting(
            key=key,
            value=value,
            description=description,
        )
        db.add(db_setting)

    await db.commit()
    await db.refresh(db_setting)
    return db_setting


async def delete_setting(db: AsyncSession, setting_id: int) -> Optional[Setting]:
    """
    Delete a setting
    """
    db_setting = await get_setting(db, setting_id)
    if not db_setting:
        return None

    await db.delete(db_setting)
    await db.commit()
    return db_setting


async def get_app_settings(db: AsyncSession) -> AppSettings:
    """
    Get application settings as a single object
    """
    # Default settings
    app_settings = AppSettings()

    # Get all settings from database
    settings = await get_settings(db)

    # Convert to dictionary for easier access
    settings_dict = {s.key: s.value for s in settings}

    # Update app settings with values from database
    if "allow_registration" in settings_dict:
        app_settings.allow_registration = (
            settings_dict["allow_registration"].lower() == "true"
        )

    if "nntp_server" in settings_dict:
        app_settings.nntp_server = settings_dict["nntp_server"]

    if "nntp_port" in settings_dict:
        app_settings.nntp_port = int(settings_dict["nntp_port"])

    if "nntp_ssl" in settings_dict:
        app_settings.nntp_ssl = settings_dict["nntp_ssl"].lower() == "true"

    if "nntp_ssl_port" in settings_dict:
        app_settings.nntp_ssl_port = int(settings_dict["nntp_ssl_port"])

    if "nntp_username" in settings_dict:
        app_settings.nntp_username = settings_dict["nntp_username"]

    if "nntp_password" in settings_dict:
        app_settings.nntp_password = settings_dict["nntp_password"]

    if "update_threads" in settings_dict:
        app_settings.update_threads = int(settings_dict["update_threads"])

    if "releases_threads" in settings_dict:
        app_settings.releases_threads = int(settings_dict["releases_threads"])

    if "postprocess_threads" in settings_dict:
        app_settings.postprocess_threads = int(settings_dict["postprocess_threads"])

    if "backfill_days" in settings_dict:
        app_settings.backfill_days = int(settings_dict["backfill_days"])

    if "retention_days" in settings_dict:
        app_settings.retention_days = int(settings_dict["retention_days"])

    return app_settings


async def update_app_settings(
    db: AsyncSession, app_settings: AppSettings
) -> Dict[str, Any]:
    """
    Update application settings from a single object
    """
    # Convert app settings to dictionary
    settings_dict = app_settings.dict()

    # Update each setting in the database
    for key, value in settings_dict.items():
        await update_setting_by_key(db, key, str(value))

    return {"status": "success", "message": "Settings updated successfully"}
