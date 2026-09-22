from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IdempotencyState(str, Enum):
    CLAIMED = "CLAIMED"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"


class IdempotencyDisposition(str, Enum):
    CLAIMED = "CLAIMED"
    RETRY_CLAIMED = "RETRY_CLAIMED"
    IN_PROGRESS = "IN_PROGRESS"
    REPLAY = "REPLAY"


class IdempotencyClaimRequest(BaseModel):
    scope: str = Field(min_length=1, max_length=255)
    idempotency_key: str = Field(min_length=1, max_length=255)
    http_method: str = Field(min_length=1, max_length=16)
    resource: str = Field(min_length=1, max_length=2048)
    request_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    owner_id: str = Field(min_length=1, max_length=255)
    request_id: UUID = Field(default_factory=uuid4)
    action_id: UUID | None = None

    @field_validator("scope", "idempotency_key", "resource", "owner_id")
    @classmethod
    def strip_non_empty_fields(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("http_method")
    @classmethod
    def normalize_http_method(cls, value: str) -> str:
        value = value.strip().upper()
        if not value or not value.isalpha():
            raise ValueError("http_method must contain letters only")
        return value


class IdempotencyRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    scope: str
    idempotency_key: str
    http_method: str
    resource: str
    request_fingerprint: str
    state: IdempotencyState
    owner_id: str | None = None
    fencing_generation: int = Field(ge=0)
    request_id: UUID
    action_id: UUID | None = None
    response_status: int | None = None
    response_body: dict[str, Any] | list[Any] | None = None
    error_code: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None


class IdempotencyClaimResult(BaseModel):
    disposition: IdempotencyDisposition
    record: IdempotencyRecord

    @property
    def should_execute(self) -> bool:
        return self.disposition in {
            IdempotencyDisposition.CLAIMED,
            IdempotencyDisposition.RETRY_CLAIMED,
        }


class RgwScopeTarget(BaseModel):
    bucket: str
    key: str | None = None
    prefix: str | None = None
    streaming: bool = False
