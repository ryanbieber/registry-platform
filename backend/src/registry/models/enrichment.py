from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import Column, DateTime, JSON, UniqueConstraint
from sqlmodel import Field

from registry.models.common import TimestampedModel, UUIDModel, utcnow


class AddressEnrichment(UUIDModel, TimestampedModel, table=True):
    __tablename__ = "address_enrichments"
    __table_args__ = (
        UniqueConstraint("address_id", "provider", name="uq_address_enrichments_address_provider"),
    )

    address_id: UUID = Field(foreign_key="addresses.id", index=True)
    provider: str = Field(index=True)
    kind: str = Field(index=True)
    status: str = Field(default="pending", index=True)
    source_url: Optional[str] = None
    retrieved_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    expires_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    raw_payload: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    error_message: Optional[str] = None


class CensusGeography(UUIDModel, TimestampedModel, table=True):
    __tablename__ = "census_geographies"

    address_enrichment_id: UUID = Field(
        foreign_key="address_enrichments.id",
        index=True,
        unique=True,
    )
    matched_address: Optional[str] = None
    matched_latitude: Optional[float] = None
    matched_longitude: Optional[float] = None
    state_abbr: Optional[str] = Field(default=None, max_length=2, index=True)
    state_fips: Optional[str] = Field(default=None, max_length=2)
    county_fips: Optional[str] = Field(default=None, max_length=5, index=True)
    county_name: Optional[str] = None
    tract: Optional[str] = None
    tract_geoid: Optional[str] = Field(default=None, index=True)
    block_group: Optional[str] = None
    block_group_geoid: Optional[str] = Field(default=None, index=True)
    benchmark: Optional[str] = None
    vintage: Optional[str] = None


class CrimeContext(UUIDModel, TimestampedModel, table=True):
    __tablename__ = "crime_contexts"

    address_enrichment_id: UUID = Field(
        foreign_key="address_enrichments.id",
        index=True,
        unique=True,
    )
    state_abbr: Optional[str] = Field(default=None, max_length=2, index=True)
    state_name: Optional[str] = None
    current_year: Optional[int] = Field(default=None, index=True)
    population: Optional[int] = None
    violent_crime: Optional[int] = None
    homicide: Optional[int] = None
    rape_legacy: Optional[int] = None
    rape_revised: Optional[int] = None
    robbery: Optional[int] = None
    aggravated_assault: Optional[int] = None
    property_crime: Optional[int] = None
    burglary: Optional[int] = None
    larceny: Optional[int] = None
    motor_vehicle_theft: Optional[int] = None
    total_agencies: Optional[int] = None
    participating_agencies: Optional[int] = None
    participation_pct: Optional[float] = None
    nibrs_participating_agencies: Optional[int] = None
    nibrs_participation_pct: Optional[float] = None
    participating_population: Optional[int] = None
    participating_population_pct: Optional[float] = None
    caveats: Optional[str] = None
