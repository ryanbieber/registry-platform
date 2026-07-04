from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from geoalchemy2 import Geometry
from sqlalchemy import Column, DateTime, JSON, Text
from sqlmodel import Field, Relationship, SQLModel

from registry.models.common import TimestampedModel, UUIDModel, utcnow


class RegistrantBase(SQLModel):
    external_id: str = Field(index=True)
    full_name: str = Field(index=True)
    date_of_birth: Optional[date] = None
    race: Optional[str] = None
    ethnicity: Optional[str] = None
    sex: Optional[str] = None
    height_cm: Optional[int] = None
    weight_kg: Optional[int] = None
    eye_color: Optional[str] = None
    hair_color: Optional[str] = None
    risk_level: Optional[str] = None
    demographics: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    last_seen: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class Registrant(UUIDModel, TimestampedModel, RegistrantBase, table=True):
    __tablename__ = "registrants"

    aliases: list["Alias"] = Relationship(back_populates="registrant")
    addresses: list["Address"] = Relationship(back_populates="registrant")
    offenses: list["Offense"] = Relationship(back_populates="registrant")
    photos: list["Photo"] = Relationship(back_populates="registrant")
    source_records: list["SourceRecord"] = Relationship(back_populates="registrant")


class Alias(UUIDModel, TimestampedModel, table=True):
    __tablename__ = "aliases"

    registrant_id: UUID = Field(foreign_key="registrants.id", index=True)
    alias_name: str = Field(index=True)
    registrant: Registrant = Relationship(back_populates="aliases")


class Address(UUIDModel, TimestampedModel, table=True):
    __tablename__ = "addresses"

    registrant_id: UUID = Field(foreign_key="registrants.id", index=True)
    line1: Optional[str] = None
    line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = Field(default=None, max_length=2)
    postal_code: Optional[str] = None
    county: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address_precision: Optional[str] = None
    location_geom: Optional[str] = Field(
        default=None,
        sa_column=Column(Geometry(geometry_type="POINT", srid=4326)),
    )
    location_wkt: Optional[str] = Field(default=None, sa_column=Column(Text))
    registrant: Registrant = Relationship(back_populates="addresses")


class Offense(UUIDModel, TimestampedModel, table=True):
    __tablename__ = "offenses"

    registrant_id: UUID = Field(foreign_key="registrants.id", index=True)
    offense_name: str
    offense_date: Optional[date] = None
    conviction_date: Optional[date] = None
    disposition: Optional[str] = None
    statute: Optional[str] = None
    victim_age: Optional[str] = None
    victim_gender: Optional[str] = None
    registrant: Registrant = Relationship(back_populates="offenses")


class Photo(UUIDModel, TimestampedModel, table=True):
    __tablename__ = "photos"

    registrant_id: UUID = Field(foreign_key="registrants.id", index=True)
    image_url: Optional[str] = None
    sha256: Optional[str] = None
    content_type: Optional[str] = None
    captured_at: Optional[datetime] = None
    registrant: Registrant = Relationship(back_populates="photos")


from registry.models.ingestion import SourceRecord  # noqa: E402
