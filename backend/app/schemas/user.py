"""Request/response schemas for users and authentication."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import UserRole


class UserBase(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr


class UserRegister(UserBase):
    # Upper bound is bcrypt's 72-byte limit, enforced here so the user gets a
    # clean 422 instead of a 500 from deep inside the hashing call.
    password: str = Field(min_length=8, max_length=72)
    # Note: role is deliberately NOT accepted here. Letting a client choose its
    # own role would let anyone POST {"role": "admin"} and bypass every
    # permission check in the app. Roles are assigned by the server.

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password is too long (max 72 bytes)")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRoleUpdate(BaseModel):
    """Admin-only role change."""

    role: UserRole


class UserStatusUpdate(BaseModel):
    """Admin-only activate/deactivate."""

    is_active: bool


class UserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    email: Optional[EmailStr] = None


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: UserRole
    is_active: bool
    created_at: datetime

    @classmethod
    def from_user(cls, user) -> "UserOut":
        """Mongo's _id is an ObjectId; the API always exposes it as a string."""
        return cls(
            id=str(user.id),
            name=user.name,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
        )


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Token lifetime in seconds")
    user: UserOut
