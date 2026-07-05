from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import anyio
from sqlmodel import Session, SQLModel, create_engine

from registry.enrichment import (
    _parse_census_payload,
    _parse_crime_payload,
    load_address_supporting_information,
    refresh_census_support,
    refresh_fbi_support,
)
from registry.models import Address, AddressEnrichment, CensusGeography, CrimeContext, Offense, Registrant
from registry.schemas import AddressSupportingInformationRead, CensusGeographyRead, CrimeContextRead
from registry.services import address_to_read, registrant_to_detail


def test_parse_census_payload_extracts_block_group() -> None:
    address = SimpleNamespace(state="DC", county="District of Columbia")
    payload = {
        "result": {
            "addressMatches": [
                {
                    "matchedAddress": "4600 Silver Hill Rd, Washington, DC, 20233",
                    "coordinates": {"x": -76.928365658124, "y": 38.845053106269},
                    "addressComponents": {"state": "DC"},
                    "geographies": {
                        "Census Block Groups": [
                            {
                                "GEOID": "240338024052",
                                "STATE": "24",
                                "COUNTY": "033",
                                "TRACT": "802405",
                                "BLKGRP": "2",
                            }
                        ]
                    },
                }
            ]
        }
    }

    normalized, error = _parse_census_payload(payload, address)

    assert error is None
    assert normalized["state_abbr"] == "DC"
    assert normalized["county_fips"] == "24033"
    assert normalized["tract_geoid"] == "24033802405"
    assert normalized["block_group_geoid"] == "240338024052"


def test_parse_crime_payload_uses_latest_estimate() -> None:
    estimates_payload = {
        "results": [
            {"year": 2022, "population": 700000, "violent_crime": 100, "caveats": None},
            {"year": 2024, "population": 710000, "violent_crime": 120, "caveats": "estimated"},
        ]
    }
    geo_payload = {
        "state_name": "District of Columbia",
        "current_year": 2024,
        "total_agencies": 10,
        "participating_agencies": 8,
        "participation_pct": 80.0,
        "nibrs_participating_agencies": 6,
        "nibrs_participation_pct": 60.0,
        "participating_population": 500000,
        "participating_population_pct": 70.0,
    }

    normalized, error = _parse_crime_payload(estimates_payload, geo_payload, "DC")

    assert error is None
    assert normalized["current_year"] == 2024
    assert normalized["violent_crime"] == 120
    assert normalized["state_name"] == "District of Columbia"
    assert normalized["participation_pct"] == 80.0


def test_refresh_support_round_trips_and_handles_fallbacks(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(
        engine,
        tables=[
            AddressEnrichment.__table__,
            CensusGeography.__table__,
            CrimeContext.__table__,
        ],
    )

    address = SimpleNamespace(
        id=uuid4(),
        line1="4600 Silver Hill Rd",
        line2=None,
        city="Washington",
        state="DC",
        postal_code="20233",
        county="Prince George's",
    )

    census_payload = {
        "result": {
            "addressMatches": [
                {
                    "matchedAddress": "4600 SILVER HILL RD, WASHINGTON, DC, 20233",
                    "coordinates": {"x": -76.928365658124, "y": 38.845053106269},
                    "addressComponents": {"state": "DC"},
                    "geographies": {
                        "Census Block Groups": [
                            {
                                "GEOID": "240338024052",
                                "STATE": "24",
                                "COUNTY": "033",
                                "TRACT": "802405",
                                "BLKGRP": "2",
                            }
                        ]
                    },
                }
            ]
        }
    }
    estimates_payload = {
        "results": [
            {"year": 2023, "population": 700000, "violent_crime": 100, "caveats": None},
            {"year": 2024, "population": 710000, "violent_crime": 120, "caveats": "estimated"},
        ]
    }
    geo_payload = {
        "state_name": "District of Columbia",
        "current_year": 2024,
        "total_agencies": 10,
        "participating_agencies": 8,
        "participation_pct": 80.0,
        "nibrs_participating_agencies": 6,
        "nibrs_participation_pct": 60.0,
        "participating_population": 500000,
        "participating_population_pct": 70.0,
    }
    responses = [census_payload, estimates_payload, geo_payload]

    async def fake_fetch_json(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr("registry.enrichment._fetch_json", fake_fetch_json)

    with Session(engine) as session:
        anyio.run(refresh_census_support, session, address)
        anyio.run(refresh_fbi_support, session, address)

        info = load_address_supporting_information(session, address.id)

    assert info.census is not None
    assert info.census.status == "completed"
    assert info.census.block_group_geoid == "240338024052"
    assert info.fbi_crime is not None
    assert info.fbi_crime.current_year == 2024
    assert info.fbi_crime.violent_crime == 120

    missing_state_address = SimpleNamespace(
        id=uuid4(),
        line1="Unknown",
        line2=None,
        city="Washington",
        state=None,
        postal_code=None,
        county=None,
    )
    with Session(engine) as session:
        anyio.run(refresh_fbi_support, session, missing_state_address)
        missing_info = load_address_supporting_information(session, missing_state_address.id)

    assert missing_info.fbi_crime is not None
    assert missing_info.fbi_crime.status == "unavailable"


def test_registrant_to_detail_includes_supporting_information(monkeypatch) -> None:
    address = Registrant(
        external_id="demo-1",
        full_name="Example Person",
        last_seen=datetime.now(timezone.utc),
    )
    detail_address = Address(
        registrant_id=uuid4(),
        line1="4600 Silver Hill Rd",
        line2=None,
        city="Washington",
        state="DC",
        postal_code="20233",
        county="Prince George's",
        latitude=38.845,
        longitude=-76.928,
        address_precision="parcel",
    )
    address.addresses = [detail_address]
    address.offenses = [
        Offense(
            registrant_id=uuid4(),
            offense_name="Example offense",
        )
    ]

    support = AddressSupportingInformationRead(
        census=CensusGeographyRead(
            status="completed",
            matched_address="4600 SILVER HILL RD, WASHINGTON, DC, 20233",
            tract_geoid="240338024052",
        ),
        fbi_crime=CrimeContextRead(
            status="completed",
            state_name="District of Columbia",
            current_year=2024,
            violent_crime=120,
        ),
    )
    monkeypatch.setattr("registry.services.load_address_supporting_information", lambda session, address_id: support)

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class FakeSession:
        def exec(self, statement):  # noqa: ANN001
            return FakeResult([detail_address])

    detail = registrant_to_detail(FakeSession(), address)

    assert detail.addresses[0].supporting_information.census is not None
    assert detail.addresses[0].supporting_information.census.tract_geoid == "240338024052"
    assert detail.addresses[0].supporting_information.fbi_crime is not None
    assert detail.addresses[0].supporting_information.fbi_crime.current_year == 2024

    serialized_address = address_to_read(detail_address, support)
    assert serialized_address.supporting_information.census is not None
