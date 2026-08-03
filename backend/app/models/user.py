"""User account collection."""

from datetime import datetime, timezone

import pymongo
from beanie import Document
from pydantic import EmailStr, Field

from app.models.enums import UserRole


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Document):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password_hash: str
    role: UserRole = UserRole.ANALYST
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "users"
        indexes = [
            # Unique index enforced by MongoDB itself, not just application
            # code. Two concurrent registrations with the same email cannot
            # both succeed - the second gets a DuplicateKeyError.
            pymongo.IndexModel([("email", pymongo.ASCENDING)], unique=True),
            pymongo.IndexModel([("role", pymongo.ASCENDING)]),
        ]

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"