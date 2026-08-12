from __future__ import annotations

import re

from pydantic import BaseModel, field_validator

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-.]+$")


class UserCreate(BaseModel):
    """Payload for POST /auth/register."""

    email: str  # validated email format
    password: str  # min 8 chars
    display_name: str  # max 64 chars

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) > 254:
            raise ValueError("email too long")
        if not _EMAIL_RE.match(v):
            raise ValueError("invalid email format")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        if len(v) > 128:
            raise ValueError("password too long")
        return v

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("display_name must not be empty")
        if len(v) > 64:
            raise ValueError("display_name must be 64 characters or fewer")
        return v


class UserLogin(BaseModel):
    """Payload for POST /auth/login."""

    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) > 128:
            raise ValueError("password too long")
        return v


class UserResponse(BaseModel):
    """Safe user payload — password_hash is NEVER included."""

    id: str
    email: str
    display_name: str
    created_at: str  # ISO 8601


class SessionResponse(BaseModel):
    """Returned once on successful login/register. Token not stored after delivery."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until expiry
