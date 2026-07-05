from collections.abc import Generator
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from registry.api.main import app
from registry.db import get_session
from registry.models import AddressEnrichment, CensusGeography, CrimeContext, Offense, Registrant


def _make_engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _create_address_table(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE addresses (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    registrant_id TEXT NOT NULL,
                    line1 TEXT,
                    line2 TEXT,
                    city TEXT,
                    state TEXT,
                    postal_code TEXT,
                    county TEXT,
                    latitude REAL,
                    longitude REAL,
                    address_precision TEXT,
                    location_geom TEXT,
                    location_wkt TEXT
                )
                """
            )
        )


def _seed_functional_data(session: Session) -> dict[str, UUID]:
    person_a = uuid4()
    person_b = uuid4()
    person_c = uuid4()
    address_a = uuid4()
    address_b = uuid4()
    address_c = uuid4()

    session.add_all(
        [
            Registrant(
                id=person_a,
                external_id="IA-1001",
                full_name="Example One",
                risk_level="Tier II",
                last_seen=datetime.now(timezone.utc),
            ),
            Registrant(
                id=person_b,
                external_id="IA-1002",
                full_name="Example Two",
                risk_level="Tier I",
                last_seen=datetime.now(timezone.utc),
            ),
            Registrant(
                id=person_c,
                external_id="IA-1003",
                full_name="Example Three",
                risk_level="Tier III",
                last_seen=datetime.now(timezone.utc),
            ),
            Offense(
                registrant_id=person_a,
                offense_name="Example offense",
                offense_date=datetime(2011, 1, 7, tzinfo=timezone.utc).date(),
                conviction_date=datetime(2011, 1, 7, tzinfo=timezone.utc).date(),
                statute="709.4",
            ),
        ]
    )
    session.commit()

    session.execute(
        text(
            """
            INSERT INTO addresses (
                id, created_at, updated_at, registrant_id, line1, line2, city, state,
                postal_code, county, latitude, longitude, address_precision, location_geom, location_wkt
            )
            VALUES (
                :id, :created_at, :updated_at, :registrant_id, :line1, :line2, :city, :state,
                :postal_code, :county, :latitude, :longitude, :address_precision, :location_geom, :location_wkt
            )
            """
        ),
        [
            {
                "id": address_a.hex,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "registrant_id": person_a.hex,
                "line1": "123 Main St",
                "line2": None,
                "city": "Des Moines",
                "state": "IA",
                "postal_code": "50309",
                "county": "Polk",
                "latitude": 41.5868,
                "longitude": -93.625,
                "address_precision": "registry",
                "location_geom": None,
                "location_wkt": None,
            },
            {
                "id": address_b.hex,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "registrant_id": person_b.hex,
                "line1": "123 Main St",
                "line2": None,
                "city": "Des Moines",
                "state": "Iowa",
                "postal_code": "50309",
                "county": "Polk",
                "latitude": 41.5868,
                "longitude": -93.625,
                "address_precision": "registry",
                "location_geom": None,
                "location_wkt": None,
            },
            {
                "id": address_c.hex,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "registrant_id": person_c.hex,
                "line1": "200 River Dr",
                "line2": None,
                "city": "Ames",
                "state": "IA",
                "postal_code": "50010",
                "county": "Story",
                "latitude": 42.0356,
                "longitude": -93.6100,
                "address_precision": "registry",
                "location_geom": None,
                "location_wkt": None,
            },
        ],
    )
    session.commit()
    return {
        "person_a": person_a,
        "person_b": person_b,
        "person_c": person_c,
        "address_a": address_a,
        "address_b": address_b,
        "address_c": address_c,
    }


def test_end_to_end_api_flow(monkeypatch) -> None:
    engine = _make_engine()
    SQLModel.metadata.create_all(
        engine,
        tables=[
            Registrant.__table__,
            Offense.__table__,
            AddressEnrichment.__table__,
            CensusGeography.__table__,
            CrimeContext.__table__,
        ],
    )
    _create_address_table(engine)

    with Session(engine) as session:
        ids = _seed_functional_data(session)

    census_payload = {
        "result": {
            "addressMatches": [
                {
                    "matchedAddress": "123 Main St, Des Moines, IA, 50309",
                    "coordinates": {"x": -93.625, "y": 41.5868},
                    "addressComponents": {"state": "IA"},
                    "geographies": {
                        "Census Block Groups": [
                            {
                                "GEOID": "191530001001",
                                "STATE": "19",
                                "COUNTY": "153",
                                "TRACT": "000100",
                                "BLKGRP": "1",
                            }
                        ]
                    },
                }
            ]
        }
    }
    estimates_payload = {
        "results": [
            {"year": 2023, "population": 3200000, "violent_crime": 1000, "caveats": None},
            {"year": 2024, "population": 3210000, "violent_crime": 990, "caveats": "estimated"},
        ]
    }
    geo_payload = {
        "state_name": "Iowa",
        "current_year": 2024,
        "total_agencies": 200,
        "participating_agencies": 180,
        "participation_pct": 90.0,
        "nibrs_participating_agencies": 160,
        "nibrs_participation_pct": 80.0,
        "participating_population": 2500000,
        "participating_population_pct": 78.0,
    }
    responses = [census_payload, estimates_payload, geo_payload]

    async def fake_fetch_json(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr("registry.enrichment._fetch_json", fake_fetch_json)

    def override_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)

        health = client.get("/health")
        registrants = client.get("/registrants")
        detail_before = client.get(f"/registrants/{ids['person_a']}")
        enrich = client.post(f"/addresses/{ids['address_a']}/enrich?force=true")
        detail_after = client.get(f"/registrants/{ids['person_a']}")
        spatial = client.get("/spatial/iowa/h3?resolution=10")
    finally:
        app.dependency_overrides.clear()

    assert health.status_code == 200
    assert registrants.status_code == 200
    assert detail_before.status_code == 200
    assert detail_after.status_code == 200
    assert enrich.status_code == 200
    assert spatial.status_code == 200

    registrant_rows = registrants.json()
    assert {row["id"] for row in registrant_rows} == {
        str(ids["person_a"]),
        str(ids["person_b"]),
        str(ids["person_c"]),
    }

    detail_payload = detail_after.json()
    assert detail_payload["id"] == str(ids["person_a"])
    assert detail_payload["addresses"][0]["supporting_information"]["census"]["block_group_geoid"] == "191530001001"
    assert detail_payload["addresses"][0]["supporting_information"]["fbi_crime"]["current_year"] == 2024

    enrich_payload = enrich.json()
    assert enrich_payload["supporting_information"]["census"]["tract_geoid"] == "19153000100"
    assert enrich_payload["supporting_information"]["fbi_crime"]["violent_crime"] == 990

    spatial_payload = spatial.json()
    assert spatial_payload["state"] == "IA"
    assert spatial_payload["total_people"] == 3
    assert all(row["person_ids"] for row in spatial_payload["cells"])
