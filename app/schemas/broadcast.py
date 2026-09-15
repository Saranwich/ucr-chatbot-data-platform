from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


Audience = Literal["all", "selected"]
BroadcastStatus = Literal["sending", "completed"]
DeliveryStatus = Literal["pending", "sending", "sent", "failed", "unknown", "skipped"]


def utf16_length(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


class BroadcastCreate(BaseModel):
    text: str
    audience: Audience
    user_ids: list[UUID] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        if utf16_length(value) > 5000:
            raise ValueError("text must be at most 5000 UTF-16 code units")
        return value

    @model_validator(mode="after")
    def validate_audience(self):
        if self.audience == "all" and self.user_ids:
            raise ValueError("user_ids must be empty when audience is all")
        if self.audience == "selected" and not self.user_ids:
            raise ValueError("user_ids is required when audience is selected")
        if len(self.user_ids) != len(set(self.user_ids)):
            raise ValueError("user_ids must not contain duplicates")
        return self


class DeliveryCounts(BaseModel):
    pending: int = 0
    sending: int = 0
    sent: int = 0
    failed: int = 0
    unknown: int = 0
    skipped: int = 0


class BroadcastSummary(BaseModel):
    id: UUID
    text: str
    audience: Audience
    user_ids: list[UUID]
    recipient_count: int
    status: BroadcastStatus
    created_at: datetime
    counts: DeliveryCounts


class BroadcastRecipient(BaseModel):
    user_id: UUID
    status: DeliveryStatus
    attempted_at: datetime | None = None
    completed_at: datetime | None = None
    response_status: int | None = None
    error: str | None = None


class BroadcastDetail(BroadcastSummary):
    recipients: list[BroadcastRecipient] = Field(default_factory=list)


class BroadcastList(BaseModel):
    items: list[BroadcastSummary]
    total: int
