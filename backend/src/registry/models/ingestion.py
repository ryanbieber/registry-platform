from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import Column, DateTime, JSON, Text
from sqlmodel import Field, Relationship, SQLModel

from registry.models.common import TimestampedModel, UUIDModel, utcnow


class IngestionRun(UUIDModel, TimestampedModel, table=True):
    __tablename__ = "ingestion_runs"

    source_name: str = Field(index=True)
    source_state: Optional[str] = Field(default=None, max_length=2)
    started_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    status: str = Field(default="pending", index=True)
    notes: Optional[str] = None

    source_records: list["SourceRecord"] = Relationship(back_populates="ingestion_run")


class SourceRecord(UUIDModel, TimestampedModel, table=True):
    __tablename__ = "source_records"

    registrant_id: Optional[UUID] = Field(default=None, foreign_key="registrants.id", index=True)
    ingestion_run_id: UUID = Field(foreign_key="ingestion_runs.id", index=True)
    source_name: str = Field(index=True)
    source_state: Optional[str] = Field(default=None, max_length=2)
    source_url: Optional[str] = None
    external_id: str = Field(index=True)
    raw_payload: dict = Field(sa_column=Column(JSON, nullable=False))
    raw_payload_path: Optional[str] = None
    raw_html: Optional[str] = Field(default=None, sa_column=Column(Text))
    normalized_payload: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    last_seen: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    registrant: Optional["Registrant"] = Relationship(back_populates="source_records")
    ingestion_run: IngestionRun = Relationship(back_populates="source_records")


from registry.models.registrant import Registrant  # noqa: E402
