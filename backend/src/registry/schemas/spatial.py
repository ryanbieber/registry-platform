from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class H3CellRead(BaseModel):
    h3_index: str
    count: int
    person_ids: list[UUID] = Field(default_factory=list)
    center_latitude: float
    center_longitude: float
    boundary: list[list[float]] = Field(default_factory=list)


class IowaH3MapRead(BaseModel):
    state: str = "IA"
    resolution: int
    total_people: int
    cells: list[H3CellRead] = Field(default_factory=list)
