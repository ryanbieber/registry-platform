from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class RegistrantListItem(BaseModel):
    id: UUID
    external_id: str
    full_name: str
    risk_level: Optional[str] = None
    last_seen: datetime


class AddressRead(BaseModel):
    line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address_precision: Optional[str] = None


class OffenseRead(BaseModel):
    offense_name: str
    offense_date: Optional[date] = None
    conviction_date: Optional[date] = None
    statute: Optional[str] = None


class RegistrantDetail(RegistrantListItem):
    date_of_birth: Optional[date] = None
    race: Optional[str] = None
    sex: Optional[str] = None
    addresses: list[AddressRead] = []
    offenses: list[OffenseRead] = []
