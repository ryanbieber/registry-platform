from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import Column, DateTime, JSON, Text, UniqueConstraint
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
    __table_args__ = (UniqueConstraint("source_name", "external_id", name="uq_source_records_source_name_external_id"),)

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


class IngestionCheckpoint(UUIDModel, TimestampedModel, table=True):
    __tablename__ = "ingestion_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "source_name",
            "source_state",
            "checkpoint_name",
            name="uq_ingestion_checkpoints_source_state_name",
        ),
    )

    source_name: str = Field(index=True)
    source_state: Optional[str] = Field(default=None, max_length=2, index=True)
    checkpoint_name: str = Field(default="default", index=True)
    cursor: Optional[str] = None
    last_external_id: Optional[str] = Field(default=None, index=True)
    last_ingestion_run_id: Optional[UUID] = Field(default=None, foreign_key="ingestion_runs.id", index=True)
    completed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    details: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    last_ingestion_run: Optional[IngestionRun] = Relationship()


from registry.models.registrant import Registrant  # noqa: E402
