from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampedModel(SQLModel):
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)


class UUIDModel(SQLModel):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
