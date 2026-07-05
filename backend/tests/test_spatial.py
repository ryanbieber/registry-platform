from collections.abc import Generator
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import h3

from registry.api.main import app
from registry.db import get_session
from registry.models import Registrant
from registry.spatial import get_iowa_h3_map


def _make_engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _seed_iowa_data(session: Session) -> dict[str, UUID]:
    person_a = uuid4()
    person_b = uuid4()
    person_c = uuid4()

    session.add_all(
        [
            Registrant(
                id=person_a,
                external_id="IA-0001",
                full_name="Example One",
                last_seen=datetime.now(timezone.utc),
            ),
            Registrant(
                id=person_b,
                external_id="IA-0002",
                full_name="Example Two",
                last_seen=datetime.now(timezone.utc),
            ),
            Registrant(
                id=person_c,
                external_id="IA-0003",
                full_name="Example Three",
                last_seen=datetime.now(timezone.utc),
            ),
        ]
    )
    session.flush()

    session.commit()

    session.execute(
        text(
            """
            INSERT INTO addresses (id, registrant_id, state, latitude, longitude)
            VALUES (:id, :registrant_id, :state, :latitude, :longitude)
            """
        ),
        [
            {
                "id": str(uuid4()),
                "registrant_id": str(person_a),
                "state": "IA",
                "latitude": 41.5868,
                "longitude": -93.625,
            },
            {
                "id": str(uuid4()),
                "registrant_id": str(person_a),
                "state": "Iowa",
                "latitude": 41.5868,
                "longitude": -93.625,
            },
            {
                "id": str(uuid4()),
                "registrant_id": str(person_b),
                "state": "IA",
                "latitude": 41.5868,
                "longitude": -93.625,
            },
            {
                "id": str(uuid4()),
                "registrant_id": str(person_c),
                "state": "IA",
                "latitude": 41.7001,
                "longitude": -93.8002,
            },
        ],
    )
    session.commit()
    return {"person_a": person_a, "person_b": person_b, "person_c": person_c}


def test_get_iowa_h3_map_groups_people_by_cell() -> None:
    engine = _make_engine()
    SQLModel.metadata.create_all(engine, tables=[Registrant.__table__])
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE addresses (
                    id TEXT PRIMARY KEY,
                    registrant_id TEXT NOT NULL,
                    state TEXT,
                    latitude REAL,
                    longitude REAL
                )
                """
            )
        )

    with Session(engine) as session:
        ids = _seed_iowa_data(session)
        result = get_iowa_h3_map(session, resolution=10)

    first_cell = h3.latlng_to_cell(41.5868, -93.625, 10)
    second_cell = h3.latlng_to_cell(41.7001, -93.8002, 10)
    cells = {cell.h3_index: cell for cell in result.cells}

    assert result.resolution == 10
    assert result.total_people == 3
    assert cells[first_cell].count == 2
    assert set(cells[first_cell].person_ids) == {ids["person_a"], ids["person_b"]}
    assert cells[second_cell].count == 1
    assert cells[second_cell].person_ids == [ids["person_c"]]
    assert len(cells[first_cell].boundary) >= 6


def test_iowa_h3_map_endpoint_returns_uuid_aggregates() -> None:
    engine = _make_engine()
    SQLModel.metadata.create_all(engine, tables=[Registrant.__table__])
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE addresses (
                    id TEXT PRIMARY KEY,
                    registrant_id TEXT NOT NULL,
                    state TEXT,
                    latitude REAL,
                    longitude REAL
                )
                """
            )
        )

    with Session(engine) as session:
        ids = _seed_iowa_data(session)

    def override_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        response = client.get("/spatial/iowa/h3?resolution=10")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    first_cell = h3.latlng_to_cell(41.5868, -93.625, 10)
    cell = next(row for row in payload["cells"] if row["h3_index"] == first_cell)

    assert payload["state"] == "IA"
    assert payload["resolution"] == 10
    assert payload["total_people"] == 3
    assert set(cell["person_ids"]) == {str(ids["person_a"]), str(ids["person_b"])}


def test_iowa_h3_map_endpoint_rejects_resolution_above_ten() -> None:
    client = TestClient(app)
    response = client.get("/spatial/iowa/h3?resolution=11")

    assert response.status_code == 422
