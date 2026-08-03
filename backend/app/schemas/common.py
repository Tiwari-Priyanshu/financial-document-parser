"""Generic response shapes reused across endpoints."""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Message(BaseModel):
    detail: str


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Standard envelope for every list endpoint. Returning a bare array is a
    common mistake - it leaves the client with no way to know the total count
    or how many pages there are.
    """

    items: list[T]
    total: int = Field(description="Total rows matching the filters, ignoring pagination")
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(cls, items: list[T], total: int, page: int, page_size: int):
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
