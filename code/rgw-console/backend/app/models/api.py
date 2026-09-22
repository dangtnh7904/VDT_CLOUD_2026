from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ApiErrorDetail(BaseModel):
    """Stable error body used by API exception handlers."""

    request_id: UUID
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    retryable: bool = False
    observed_state: dict[str, Any] | None = None


class ApiErrorResponse(BaseModel):
    detail: ApiErrorDetail
