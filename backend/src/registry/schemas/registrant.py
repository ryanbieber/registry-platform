from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RegistrantListItem(BaseModel):
    id: UUID
    external_id: str
    full_name: str
    risk_level: Optional[str] = None
    last_seen: datetime


class AddressRead(BaseModel):
    id: UUID
    line1: Optional[str] = None
    line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    county: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address_precision: Optional[str] = None
    supporting_information: AddressSupportingInformationRead = Field(default_factory=lambda: AddressSupportingInformationRead())


class CensusGeographyRead(BaseModel):
    provider: str = "census"
    kind: str = "census_geography"
    status: str
    source_url: Optional[str] = None
    retrieved_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    error_message: Optional[str] = None
    matched_address: Optional[str] = None
    matched_latitude: Optional[float] = None
    matched_longitude: Optional[float] = None
    state_abbr: Optional[str] = None
    state_fips: Optional[str] = None
    county_fips: Optional[str] = None
    county_name: Optional[str] = None
    tract: Optional[str] = None
    tract_geoid: Optional[str] = None
    block_group: Optional[str] = None
    block_group_geoid: Optional[str] = None
    benchmark: Optional[str] = None
    vintage: Optional[str] = None


class CrimeContextRead(BaseModel):
    provider: str = "fbi"
    kind: str = "crime_context"
    status: str
    source_url: Optional[str] = None
    retrieved_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    error_message: Optional[str] = None
    state_abbr: Optional[str] = None
    state_name: Optional[str] = None
    current_year: Optional[int] = None
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


class AddressSupportingInformationRead(BaseModel):
    census: Optional[CensusGeographyRead] = None
    fbi_crime: Optional[CrimeContextRead] = None


class OffenseRead(BaseModel):
    offense_name: str
    offense_date: Optional[date] = None
    conviction_date: Optional[date] = None
    statute: Optional[str] = None


class RegistrantDetail(RegistrantListItem):
    date_of_birth: Optional[date] = None
    race: Optional[str] = None
    sex: Optional[str] = None
    addresses: list[AddressRead] = Field(default_factory=list)
    offenses: list[OffenseRead] = Field(default_factory=list)
