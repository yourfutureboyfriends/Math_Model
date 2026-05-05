"""Authentication models."""

from typing import List, Optional
from pydantic import BaseModel


class User(BaseModel):
    username: str
    role: str
    display_name: str
    permissions: List[str]


class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    role: str
    display_name: str
    permissions: List[str]
    expires_in: int
