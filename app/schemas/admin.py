"""
Admin schemas for web routes
"""

from typing import Optional

from pydantic import BaseModel, Field


class GroupDiscoveryRequest(BaseModel):
    """
    Schema for group discovery request from web interface
    """

    pattern: str = Field(default="*", description="Pattern to filter newsgroups")
    active: bool = Field(
        default=False, description="Whether to set discovered groups as active"
    )
