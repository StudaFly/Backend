from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ResponseBase(BaseModel, Generic[T]):
    data: T
    message: str = "OK"


class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    total: int
    page: int
    per_page: int


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
