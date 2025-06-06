from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SettingBase(BaseModel):
    """
    Base schema for settings
    """

    key: str
    value: Optional[str] = None
    description: Optional[str] = None


class SettingCreate(SettingBase):
    """
    Schema for creating a setting
    """

    pass


class SettingUpdate(BaseModel):
    """
    Schema for updating a setting
    """

    value: Optional[str] = None
    description: Optional[str] = None


class SettingResponse(SettingBase):
    """
    Schema for setting response
    """

    id: int

    class Config:
        from_attributes = True


class AppSettings(BaseModel):
    """
    Schema for application settings form
    """

    # Registration settings
    allow_registration: bool = Field(
        default=True, description="Allow new user registration"
    )

    # NNTP settings
    nntp_server: str = Field(default="", description="NNTP server hostname")
    nntp_port: int = Field(default=119, description="NNTP server port")
    nntp_ssl: bool = Field(default=False, description="Use SSL for NNTP connection")
    nntp_ssl_port: int = Field(default=563, description="NNTP SSL port")
    nntp_username: str = Field(default="", description="NNTP username")
    nntp_password: str = Field(default="", description="NNTP password")

    # Indexer settings
    update_threads: int = Field(
        default=1, description="Number of threads for updating groups"
    )
    releases_threads: int = Field(
        default=1, description="Number of threads for processing releases"
    )
    postprocess_threads: int = Field(
        default=1, description="Number of threads for post-processing"
    )
    backfill_days: int = Field(default=3, description="Number of days to backfill")
    retention_days: int = Field(
        default=1100, description="Number of days to retain articles"
    )
