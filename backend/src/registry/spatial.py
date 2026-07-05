from __future__ import annotations

from collections import defaultdict
from uuid import UUID

import h3
from sqlalchemy import func, select
from sqlmodel import Session

from registry.models import Address
from registry.schemas import H3CellRead, IowaH3MapRead


def _boundary_to_coordinates(cell_index: str) -> list[list[float]]:
    return [[longitude, latitude] for latitude, longitude in h3.cell_to_boundary(cell_index)]


def get_iowa_h3_map(session: Session, *, resolution: int = 10) -> IowaH3MapRead:
    resolution = max(0, min(resolution, 10))
    statement = select(Address.registrant_id, Address.latitude, Address.longitude).where(
        Address.latitude.is_not(None),
        Address.longitude.is_not(None),
        func.upper(Address.state).in_(("IA", "IOWA")),
    )
    rows = session.exec(statement).all()

    people_by_cell: dict[str, set[UUID]] = defaultdict(set)
    centers_by_cell: dict[str, tuple[float, float]] = {}
    boundaries_by_cell: dict[str, list[list[float]]] = {}
    all_people: set[UUID] = set()

    for registrant_id, latitude, longitude in rows:
        if registrant_id is None or latitude is None or longitude is None:
            continue
        registrant_uuid = registrant_id if isinstance(registrant_id, UUID) else UUID(str(registrant_id))
        cell_index = h3.latlng_to_cell(latitude, longitude, resolution)
        people_by_cell[cell_index].add(registrant_uuid)
        all_people.add(registrant_uuid)
        if cell_index not in centers_by_cell:
            center_latitude, center_longitude = h3.cell_to_latlng(cell_index)
            centers_by_cell[cell_index] = (center_latitude, center_longitude)
            boundaries_by_cell[cell_index] = _boundary_to_coordinates(cell_index)

    cells = [
        H3CellRead(
            h3_index=cell_index,
            count=len(person_ids),
            person_ids=sorted(person_ids, key=str),
            center_latitude=centers_by_cell[cell_index][0],
            center_longitude=centers_by_cell[cell_index][1],
            boundary=boundaries_by_cell[cell_index],
        )
        for cell_index, person_ids in sorted(people_by_cell.items(), key=lambda item: (-len(item[1]), item[0]))
    ]

    return IowaH3MapRead(
        resolution=resolution,
        total_people=len(all_people),
        cells=cells,
    )
