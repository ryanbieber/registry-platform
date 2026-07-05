from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from sqlalchemy import delete
from sqlmodel import Session, select

from registry.models import Address, Alias, Offense, Photo, Registrant, SourceRecord
from registry.models.common import utcnow

_NESTED_COLLECTION_KEYS = {
    "aliases",
    "addresses",
    "offenses",
    "photos",
}


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _coerce_date(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None
    return None


def _iter_records_by_external_id(
    session: Session,
    source_name: str,
    external_ids: list[str],
) -> tuple[dict[str, Registrant], dict[str, SourceRecord]]:
    registrants_by_external_id: dict[str, Registrant] = {}
    source_records_by_external_id: dict[str, SourceRecord] = {}

    if not external_ids:
        return registrants_by_external_id, source_records_by_external_id

    registrant_rows = session.exec(
        select(Registrant).where(Registrant.external_id.in_(external_ids))
    ).all()
    registrants_by_external_id = {row.external_id: row for row in registrant_rows}

    source_record_rows = session.exec(
        select(SourceRecord).where(
            SourceRecord.source_name == source_name,
            SourceRecord.external_id.in_(external_ids),
        )
    ).all()
    source_records_by_external_id = {row.external_id: row for row in source_record_rows}
    return registrants_by_external_id, source_records_by_external_id


def _replace_children(
    session: Session,
    registrant_id,
    model: type,
    rows: Iterable[dict[str, Any]],
    factory,
) -> int:
    row_list = list(rows)
    if not row_list:
        return 0
    session.exec(delete(model).where(model.registrant_id == registrant_id))
    inserted = 0
    for row in row_list:
        session.add(factory(row))
        inserted += 1
    return inserted


def persist_normalized_records(
    session: Session,
    *,
    source_name: str,
    source_state: str | None,
    ingestion_run_id,
    normalized_records: list[dict[str, Any]],
    dry_run: bool = True,
) -> dict[str, Any]:
    stats = {
        "records_seen": len(normalized_records),
        "registrants_upserted": 0,
        "source_records_upserted": 0,
        "aliases_upserted": 0,
        "addresses_upserted": 0,
        "offenses_upserted": 0,
        "photos_upserted": 0,
    }

    external_ids = [record["external_id"] for record in normalized_records if record.get("external_id")]
    registrants_by_external_id, source_records_by_external_id = _iter_records_by_external_id(
        session, source_name, external_ids
    )

    for record in normalized_records:
        external_id = record.get("external_id")
        if not external_id:
            continue

        source_payload = record.get("raw_payload") or record
        normalized_payload = {
            key: value
            for key, value in record.items()
            if key not in {"raw_payload", "raw_html", *(_NESTED_COLLECTION_KEYS)}
        }
        registrant = registrants_by_external_id.get(external_id)
        if registrant is None:
            registrant = Registrant(
                external_id=external_id,
                full_name=record.get("full_name") or record.get("name") or external_id,
            )
            registrants_by_external_id[external_id] = registrant
            stats["registrants_upserted"] += 1

        registrant.full_name = record.get("full_name") or record.get("name") or registrant.full_name
        registrant.date_of_birth = _coerce_date(record.get("date_of_birth")) or registrant.date_of_birth
        registrant.race = record.get("race") or None
        registrant.ethnicity = record.get("ethnicity") or None
        registrant.sex = record.get("sex") or None
        registrant.height_cm = record.get("height_cm") or None
        registrant.weight_kg = record.get("weight_kg") or None
        registrant.eye_color = record.get("eye_color") or None
        registrant.hair_color = record.get("hair_color") or None
        registrant.risk_level = record.get("risk_level") or None
        registrant.demographics = record.get("demographics") or None
        registrant.last_seen = _coerce_datetime(record.get("last_seen")) or utcnow()

        if not dry_run:
            session.add(registrant)
            session.flush()

            stats["aliases_upserted"] += _replace_children(
                session,
                registrant.id,
                Alias,
                (
                    {"alias_name": alias} if isinstance(alias, str) else alias
                    for alias in (record.get("aliases") or [])
                ),
                lambda row: Alias(registrant_id=registrant.id, alias_name=row["alias_name"]),
            )
            stats["addresses_upserted"] += _replace_children(
                session,
                registrant.id,
                Address,
                record.get("addresses") or [],
                lambda row: Address(
                    registrant_id=registrant.id,
                    line1=row.get("line1"),
                    line2=row.get("line2"),
                    city=row.get("city"),
                    state=row.get("state"),
                    postal_code=row.get("postal_code"),
                    county=row.get("county"),
                    latitude=row.get("latitude"),
                    longitude=row.get("longitude"),
                    address_precision=row.get("address_precision"),
                    location_geom=row.get("location_geom"),
                    location_wkt=row.get("location_wkt"),
                ),
            )
            stats["offenses_upserted"] += _replace_children(
                session,
                registrant.id,
                Offense,
                record.get("offenses") or [],
                lambda row: Offense(
                    registrant_id=registrant.id,
                    offense_name=row.get("offense_name") or row.get("name") or "Unknown offense",
                    offense_date=_coerce_date(row.get("offense_date")),
                    conviction_date=_coerce_date(row.get("conviction_date")),
                    disposition=row.get("disposition"),
                    statute=row.get("statute"),
                    victim_age=row.get("victim_age"),
                    victim_gender=row.get("victim_gender"),
                ),
            )
            stats["photos_upserted"] += _replace_children(
                session,
                registrant.id,
                Photo,
                record.get("photos") or [],
                lambda row: Photo(
                    registrant_id=registrant.id,
                    image_url=row.get("image_url"),
                    sha256=row.get("sha256"),
                    content_type=row.get("content_type"),
                    captured_at=_coerce_datetime(row.get("captured_at")),
                ),
            )

        source_record = source_records_by_external_id.get(external_id)
        if source_record is None:
            source_record = SourceRecord(
                registrant_id=registrant.id if registrant.id else None,
                ingestion_run_id=ingestion_run_id,
                source_name=source_name,
                source_state=source_state,
                source_url=record.get("source_url"),
                external_id=external_id,
                raw_payload=source_payload,
                normalized_payload=normalized_payload,
            )
            source_records_by_external_id[external_id] = source_record
            stats["source_records_upserted"] += 1
        else:
            source_record.registrant_id = registrant.id if registrant.id else None
            source_record.ingestion_run_id = ingestion_run_id
            source_record.source_state = source_state
            source_record.source_url = record.get("source_url")
            source_record.raw_payload = source_payload
            source_record.normalized_payload = normalized_payload
            source_record.last_seen = _coerce_datetime(record.get("last_seen")) or utcnow()

        if not dry_run:
            session.add(source_record)

    return stats
