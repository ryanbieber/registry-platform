from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from types import SimpleNamespace
from uuid import UUID

import httpx
from sqlmodel import Session, select

from registry.config import settings
from registry.models import Address, AddressEnrichment, CensusGeography, CrimeContext
from registry.schemas import AddressSupportingInformationRead, CensusGeographyRead, CrimeContextRead

ADDRESS_ENRICHMENT_PROVIDER_CENSUS = "census"
ADDRESS_ENRICHMENT_PROVIDER_FBI = "fbi"
ADDRESS_ENRICHMENT_KIND_CENSUS = "census_geography"
ADDRESS_ENRICHMENT_KIND_FBI = "crime_context"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _expires_at(days: int) -> datetime:
    return _utcnow() + timedelta(days=days)


def _address_query(address: Address) -> str | None:
    parts = [address.line1, address.line2, address.city, address.state, address.postal_code]
    joined = ", ".join(part for part in parts if part)
    return joined or None


async def _fetch_json(url: str, *, params: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
        response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()


def _upsert_address_enrichment(
    session: Session,
    *,
    address_id: UUID,
    provider: str,
    kind: str,
    status: str,
    source_url: str | None,
    raw_payload: dict[str, Any],
    error_message: str | None = None,
    expires_days: int,
) -> AddressEnrichment:
    stmt = select(AddressEnrichment).where(
        AddressEnrichment.address_id == address_id,
        AddressEnrichment.provider == provider,
    )
    row = session.exec(stmt).first()
    if row is None:
        row = AddressEnrichment(
            address_id=address_id,
            provider=provider,
            kind=kind,
            status=status,
            source_url=source_url,
            retrieved_at=_utcnow(),
            expires_at=_expires_at(expires_days),
            raw_payload=raw_payload,
            error_message=error_message,
        )
    else:
        row.kind = kind
        row.status = status
        row.source_url = source_url
        row.retrieved_at = _utcnow()
        row.expires_at = _expires_at(expires_days)
        row.raw_payload = raw_payload
        row.error_message = error_message
        row.updated_at = _utcnow()

    session.add(row)
    session.flush()
    return row


def _upsert_census_geography(
    session: Session,
    *,
    address_enrichment_id: UUID,
    data: dict[str, Any],
) -> CensusGeography:
    stmt = select(CensusGeography).where(CensusGeography.address_enrichment_id == address_enrichment_id)
    row = session.exec(stmt).first()
    if row is None:
        row = CensusGeography(address_enrichment_id=address_enrichment_id, **data)
    else:
        for key, value in data.items():
            setattr(row, key, value)
        row.updated_at = _utcnow()
    session.add(row)
    session.flush()
    return row


def _upsert_crime_context(
    session: Session,
    *,
    address_enrichment_id: UUID,
    data: dict[str, Any],
) -> CrimeContext:
    stmt = select(CrimeContext).where(CrimeContext.address_enrichment_id == address_enrichment_id)
    row = session.exec(stmt).first()
    if row is None:
        row = CrimeContext(address_enrichment_id=address_enrichment_id, **data)
    else:
        for key, value in data.items():
            setattr(row, key, value)
        row.updated_at = _utcnow()
    session.add(row)
    session.flush()
    return row


def _parse_census_payload(payload: dict[str, Any], address: Address) -> tuple[dict[str, Any] | None, str | None]:
    matches = payload.get("result", {}).get("addressMatches", []) or []
    if not matches:
        return None, "No Census geocoder match found for address"

    match = matches[0]
    geographies = match.get("geographies", {}) or {}
    block_groups = geographies.get("Census Block Groups", []) or []
    block_group = block_groups[0] if block_groups else {}
    address_components = match.get("addressComponents", {}) or {}
    coordinates = match.get("coordinates", {}) or {}

    state_fips = block_group.get("STATE")
    county_fips = block_group.get("COUNTY")
    tract = block_group.get("TRACT")
    block_group_code = block_group.get("BLKGRP") or block_group.get("BLOCK_GROUP")

    data = {
        "matched_address": match.get("matchedAddress"),
        "matched_latitude": coordinates.get("y"),
        "matched_longitude": coordinates.get("x"),
        "state_abbr": address_components.get("state") or address.state,
        "state_fips": state_fips,
        "county_fips": f"{state_fips}{county_fips}" if state_fips and county_fips else None,
        "county_name": address.county,
        "tract": tract,
        "tract_geoid": f"{state_fips}{county_fips}{tract}" if state_fips and county_fips and tract else None,
        "block_group": block_group_code,
        "block_group_geoid": block_group.get("GEOID"),
        "benchmark": "Public_AR_Current",
        "vintage": "Current_Current",
    }
    return data, None


def _parse_crime_payload(
    estimates_payload: dict[str, Any],
    geo_payload: dict[str, Any],
    state_abbr: str,
) -> tuple[dict[str, Any] | None, str | None]:
    estimates = estimates_payload.get("results", []) or []
    latest_estimate = max(estimates, key=lambda item: item.get("year", 0), default=None)
    if latest_estimate is None:
        return None, "No FBI estimates were returned for the selected state"

    data = {
        "state_abbr": latest_estimate.get("state_abbr") or state_abbr,
        "state_name": geo_payload.get("state_name"),
        "current_year": geo_payload.get("current_year") or latest_estimate.get("year"),
        "population": latest_estimate.get("population"),
        "violent_crime": latest_estimate.get("violent_crime"),
        "homicide": latest_estimate.get("homicide"),
        "rape_legacy": latest_estimate.get("rape_legacy"),
        "rape_revised": latest_estimate.get("rape_revised"),
        "robbery": latest_estimate.get("robbery"),
        "aggravated_assault": latest_estimate.get("aggravated_assault"),
        "property_crime": latest_estimate.get("property_crime"),
        "burglary": latest_estimate.get("burglary"),
        "larceny": latest_estimate.get("larceny"),
        "motor_vehicle_theft": latest_estimate.get("motor_vehicle_theft"),
        "total_agencies": geo_payload.get("total_agencies"),
        "participating_agencies": geo_payload.get("participating_agencies"),
        "participation_pct": geo_payload.get("participation_pct"),
        "nibrs_participating_agencies": geo_payload.get("nibrs_participating_agencies"),
        "nibrs_participation_pct": geo_payload.get("nibrs_participation_pct"),
        "participating_population": geo_payload.get("participating_population"),
        "participating_population_pct": geo_payload.get("participating_population_pct"),
        "caveats": latest_estimate.get("caveats"),
    }
    return data, None


async def refresh_census_support(session: Session, address: Address, *, force: bool = False) -> AddressEnrichment:
    existing = session.exec(
        select(AddressEnrichment).where(
            AddressEnrichment.address_id == address.id,
            AddressEnrichment.provider == ADDRESS_ENRICHMENT_PROVIDER_CENSUS,
        )
    ).first()
    if existing and not force and existing.expires_at and existing.expires_at > _utcnow() and existing.status == "completed":
        return existing

    query = _address_query(address)
    if query is None:
        enrichment = _upsert_address_enrichment(
            session,
            address_id=address.id,
            provider=ADDRESS_ENRICHMENT_PROVIDER_CENSUS,
            kind=ADDRESS_ENRICHMENT_KIND_CENSUS,
            status="unavailable",
            source_url=settings.census_geocoder_url,
            raw_payload={},
            error_message="Address is missing enough fields for Census geocoding",
            expires_days=settings.census_enrichment_ttl_days,
        )
        session.commit()
        session.refresh(enrichment)
        return enrichment

    params = {
        "address": query,
        "benchmark": "Public_AR_Current",
        "vintage": "Current_Current",
        "format": "json",
        "layers": "10",
    }
    try:
        payload = await _fetch_json(settings.census_geocoder_url, params=params)
        normalized, error_message = _parse_census_payload(payload, address)
        enrichment = _upsert_address_enrichment(
            session,
            address_id=address.id,
            provider=ADDRESS_ENRICHMENT_PROVIDER_CENSUS,
            kind=ADDRESS_ENRICHMENT_KIND_CENSUS,
            status="completed" if normalized else "unavailable",
            source_url=str(httpx.URL(settings.census_geocoder_url, params=params)),
            raw_payload=payload,
            error_message=error_message,
            expires_days=settings.census_enrichment_ttl_days,
        )
        if normalized:
            _upsert_census_geography(session, address_enrichment_id=enrichment.id, data=normalized)
        session.commit()
        session.refresh(enrichment)
        return enrichment
    except (httpx.HTTPError, ValueError) as exc:
        enrichment = _upsert_address_enrichment(
            session,
            address_id=address.id,
            provider=ADDRESS_ENRICHMENT_PROVIDER_CENSUS,
            kind=ADDRESS_ENRICHMENT_KIND_CENSUS,
            status="error",
            source_url=str(httpx.URL(settings.census_geocoder_url, params=params)),
            raw_payload={},
            error_message=str(exc),
            expires_days=settings.census_error_ttl_days,
        )
        session.commit()
        session.refresh(enrichment)
        return enrichment


async def refresh_fbi_support(session: Session, address: Address, *, force: bool = False) -> AddressEnrichment:
    existing = session.exec(
        select(AddressEnrichment).where(
            AddressEnrichment.address_id == address.id,
            AddressEnrichment.provider == ADDRESS_ENRICHMENT_PROVIDER_FBI,
        )
    ).first()
    if existing and not force and existing.expires_at and existing.expires_at > _utcnow() and existing.status == "completed":
        return existing

    state_abbr = address.state
    if not state_abbr:
        enrichment = _upsert_address_enrichment(
            session,
            address_id=address.id,
            provider=ADDRESS_ENRICHMENT_PROVIDER_FBI,
            kind=ADDRESS_ENRICHMENT_KIND_FBI,
            status="unavailable",
            source_url=settings.fbi_state_context_url_template.format(state_abbr=""),
            raw_payload={},
            error_message="Address is missing a state code for FBI enrichment",
            expires_days=settings.fbi_enrichment_ttl_days,
        )
        session.commit()
        session.refresh(enrichment)
        return enrichment

    estimates_url = settings.fbi_state_estimates_url_template.format(state_abbr=state_abbr.upper())
    geo_url = settings.fbi_state_geo_url_template.format(state_abbr=state_abbr.upper())
    params = {"api_key": settings.fbi_api_key}
    try:
        estimates_payload = await _fetch_json(estimates_url, params=params)
        geo_payload = await _fetch_json(geo_url, params=params)
        normalized, error_message = _parse_crime_payload(estimates_payload, geo_payload, state_abbr.upper())
        enrichment = _upsert_address_enrichment(
            session,
            address_id=address.id,
            provider=ADDRESS_ENRICHMENT_PROVIDER_FBI,
            kind=ADDRESS_ENRICHMENT_KIND_FBI,
            status="completed" if normalized else "unavailable",
            source_url=estimates_url,
            raw_payload={"estimates": estimates_payload, "geo": geo_payload},
            error_message=error_message,
            expires_days=settings.fbi_enrichment_ttl_days,
        )
        if normalized:
            _upsert_crime_context(session, address_enrichment_id=enrichment.id, data=normalized)
        session.commit()
        session.refresh(enrichment)
        return enrichment
    except (httpx.HTTPError, ValueError) as exc:
        enrichment = _upsert_address_enrichment(
            session,
            address_id=address.id,
            provider=ADDRESS_ENRICHMENT_PROVIDER_FBI,
            kind=ADDRESS_ENRICHMENT_KIND_FBI,
            status="error",
            source_url=estimates_url,
            raw_payload={},
            error_message=str(exc),
            expires_days=settings.fbi_error_ttl_days,
        )
        session.commit()
        session.refresh(enrichment)
        return enrichment


async def refresh_address_supporting_information(
    session: Session,
    address_id: UUID | str,
    *,
    force: bool = False,
) -> Address | None:
    row = session.exec(
        select(
            Address.id,
            Address.registrant_id,
            Address.line1,
            Address.line2,
            Address.city,
            Address.state,
            Address.postal_code,
            Address.county,
            Address.latitude,
            Address.longitude,
            Address.address_precision,
        ).where(Address.id == address_id)
    ).first()
    if row is None:
        return None

    address = SimpleNamespace(
        id=row[0],
        registrant_id=row[1],
        line1=row[2],
        line2=row[3],
        city=row[4],
        state=row[5],
        postal_code=row[6],
        county=row[7],
        latitude=row[8],
        longitude=row[9],
        address_precision=row[10],
    )

    await refresh_census_support(session, address, force=force)
    await refresh_fbi_support(session, address, force=force)
    return address


def load_address_supporting_information(session: Session, address_id: UUID | str) -> AddressSupportingInformationRead:
    census_row = session.exec(
        select(AddressEnrichment).where(
            AddressEnrichment.address_id == address_id,
            AddressEnrichment.provider == ADDRESS_ENRICHMENT_PROVIDER_CENSUS,
        )
    ).first()
    census_data = None
    if census_row is not None:
        geography = session.exec(
            select(CensusGeography).where(CensusGeography.address_enrichment_id == census_row.id)
        ).first()
        census_data = CensusGeographyRead(
            provider=census_row.provider,
            kind=census_row.kind,
            status=census_row.status,
            source_url=census_row.source_url,
            retrieved_at=census_row.retrieved_at,
            expires_at=census_row.expires_at,
            error_message=census_row.error_message,
            matched_address=geography.matched_address if geography else None,
            matched_latitude=geography.matched_latitude if geography else None,
            matched_longitude=geography.matched_longitude if geography else None,
            state_abbr=geography.state_abbr if geography else None,
            state_fips=geography.state_fips if geography else None,
            county_fips=geography.county_fips if geography else None,
            county_name=geography.county_name if geography else None,
            tract=geography.tract if geography else None,
            tract_geoid=geography.tract_geoid if geography else None,
            block_group=geography.block_group if geography else None,
            block_group_geoid=geography.block_group_geoid if geography else None,
            benchmark=geography.benchmark if geography else None,
            vintage=geography.vintage if geography else None,
        )

    crime_row = session.exec(
        select(AddressEnrichment).where(
            AddressEnrichment.address_id == address_id,
            AddressEnrichment.provider == ADDRESS_ENRICHMENT_PROVIDER_FBI,
        )
    ).first()
    crime_data = None
    if crime_row is not None:
        context = session.exec(
            select(CrimeContext).where(CrimeContext.address_enrichment_id == crime_row.id)
        ).first()
        crime_data = CrimeContextRead(
            provider=crime_row.provider,
            kind=crime_row.kind,
            status=crime_row.status,
            source_url=crime_row.source_url,
            retrieved_at=crime_row.retrieved_at,
            expires_at=crime_row.expires_at,
            error_message=crime_row.error_message,
            state_abbr=context.state_abbr if context else None,
            state_name=context.state_name if context else None,
            current_year=context.current_year if context else None,
            population=context.population if context else None,
            violent_crime=context.violent_crime if context else None,
            homicide=context.homicide if context else None,
            rape_legacy=context.rape_legacy if context else None,
            rape_revised=context.rape_revised if context else None,
            robbery=context.robbery if context else None,
            aggravated_assault=context.aggravated_assault if context else None,
            property_crime=context.property_crime if context else None,
            burglary=context.burglary if context else None,
            larceny=context.larceny if context else None,
            motor_vehicle_theft=context.motor_vehicle_theft if context else None,
            total_agencies=context.total_agencies if context else None,
            participating_agencies=context.participating_agencies if context else None,
            participation_pct=context.participation_pct if context else None,
            nibrs_participating_agencies=context.nibrs_participating_agencies if context else None,
            nibrs_participation_pct=context.nibrs_participation_pct if context else None,
            participating_population=context.participating_population if context else None,
            participating_population_pct=context.participating_population_pct if context else None,
            caveats=context.caveats if context else None,
        )

    return AddressSupportingInformationRead(census=census_data, fbi_crime=crime_data)
