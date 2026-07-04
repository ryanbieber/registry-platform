from datetime import datetime, timezone

from sqlmodel import Session, select

from registry.models import IngestionRun, Registrant
from registry.schemas import RegistrantDetail, RegistrantListItem, SourceSummary
from registry.sources import get_connector, list_connectors


def list_registrants(session: Session) -> list[RegistrantListItem]:
    rows = session.exec(select(Registrant)).all()
    return [
        RegistrantListItem(
            id=row.id,
            external_id=row.external_id,
            full_name=row.full_name,
            risk_level=row.risk_level,
            last_seen=row.last_seen,
        )
        for row in rows
    ]


def get_registrant(session: Session, registrant_id: str) -> RegistrantDetail | None:
    row = session.get(Registrant, registrant_id)
    if row is None:
        return None
    return RegistrantDetail(
        id=row.id,
        external_id=row.external_id,
        full_name=row.full_name,
        risk_level=row.risk_level,
        last_seen=row.last_seen,
        date_of_birth=row.date_of_birth,
        race=row.race,
        sex=row.sex,
        addresses=[
            {
                "line1": address.line1,
                "city": address.city,
                "state": address.state,
                "postal_code": address.postal_code,
                "latitude": address.latitude,
                "longitude": address.longitude,
                "address_precision": address.address_precision,
            }
            for address in row.addresses
        ],
        offenses=[
            {
                "offense_name": offense.offense_name,
                "offense_date": offense.offense_date,
                "conviction_date": offense.conviction_date,
                "statute": offense.statute,
            }
            for offense in row.offenses
        ],
    )


def list_sources() -> list[SourceSummary]:
    return [
        SourceSummary(
            name=connector.name,
            state=connector.state,
            enabled=True,
            supports_fetch=True,
            notes="Skeleton connector only. Implement gentle, compliant ingestion per source.",
        )
        for connector in list_connectors()
    ]


async def ingest_source(session: Session, source: str, *, dry_run: bool = True, limit: int | None = None) -> IngestionRun:
    connector = get_connector(source)
    run = IngestionRun(
        source_name=connector.name,
        source_state=connector.state,
        status="running",
        notes="Skeleton ingestion run. No live scraping or aggressive crawling implemented.",
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    raw_payloads = await connector.fetch(limit=limit)
    parsed = connector.parse(raw_payloads)
    normalized = connector.normalize(parsed)
    connector.upsert(session, normalized, dry_run=dry_run)

    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    session.add(run)
    session.commit()
    session.refresh(run)
    return run
