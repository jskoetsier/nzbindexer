from typing import Optional

from pydantic import BaseModel, Field


class Token(BaseModel):
    """
    Token schema for authentication
    """
    access_token: str
    token_type: str


class TokenPayload(BaseModel):
    """
    Token payload schema
    """
    sub: Optional[int] = None
    exp: Optional[int] = None
