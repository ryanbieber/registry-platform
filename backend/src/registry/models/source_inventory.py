from __future__ import annotations

from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from registry.models.common import TimestampedModel, UUIDModel


class RegistrySource(UUIDModel, TimestampedModel, table=True):
    __tablename__ = "registry_sources"
    __table_args__ = (
        UniqueConstraint("state", "jurisdiction_type", name="uq_registry_sources_state_jurisdiction"),
    )

    state: str = Field(index=True)
    jurisdiction_type: str = Field(index=True)
    official_registry_url: str
    access_surface: str = Field(index=True)
    recommended_acquisition_path: str
    notes: Optional[str] = None
    source_directory_name: str = Field(default="NSOPW All Registries")
    source_directory_url: str = Field(default="https://www.nsopw.gov/all-registries")
    source_checked_on: str = Field(default="2026-07-04")
