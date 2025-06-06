from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class NewsgroupDiscoveryRequest(BaseModel):
    """
    Schema for newsgroup discovery request
    """

    pattern: str = Field(
        default="*",
        description="Pattern to filter newsgroups (e.g., 'alt.*', 'comp.sys.*')",
    )
    active: bool = Field(
        default=False,
        description="Whether to set discovered groups as active",
    )


class NewsgroupDiscoveryResponse(BaseModel):
    """
    Schema for newsgroup discovery response
    """

    total: int = Field(..., description="Total number of newsgroups found")
    added: int = Field(..., description="Number of newsgroups added")
    updated: int = Field(..., description="Number of newsgroups updated")
    skipped: int = Field(..., description="Number of newsgroups skipped")
    failed: int = Field(..., description="Number of newsgroups that failed to process")
