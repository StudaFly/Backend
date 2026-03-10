from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

T = TypeVar("T")


class StudaFlyBaseModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class ResponseBase(StudaFlyBaseModel, Generic[T]):
    data: T
    message: str = "OK"


class PaginatedResponse(StudaFlyBaseModel, Generic[T]):
    data: list[T]
    total: int
    page: int
    per_page: int


class ErrorDetail(StudaFlyBaseModel):
    code: str
    message: str
    details: Any = None


class ErrorResponse(StudaFlyBaseModel):
    error: ErrorDetail
