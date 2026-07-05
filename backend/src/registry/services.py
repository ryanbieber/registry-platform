from datetime import datetime, timezone
from uuid import UUID

from sqlmodel import Session, select
from sqlalchemy.orm import load_only

from registry.enrichment import load_address_supporting_information
from registry.models import Address, IngestionCheckpoint, IngestionRun, Registrant, RegistrySource
from registry.schemas import (
    AddressRead,
    AddressSupportingInformationRead,
    RegistrantDetail,
    RegistrantListItem,
    SourceSummary,
)
from registry.sources import get_connector, list_connectors


def load_ingestion_checkpoint(
    session: Session,
    *,
    source_name: str,
    source_state: str | None,
    checkpoint_name: str = "default",
) -> IngestionCheckpoint | None:
    statement = select(IngestionCheckpoint).where(
        IngestionCheckpoint.source_name == source_name,
        IngestionCheckpoint.source_state == source_state,
        IngestionCheckpoint.checkpoint_name == checkpoint_name,
    )
    return session.exec(statement).first()


def save_ingestion_checkpoint(
    session: Session,
    *,
    source_name: str,
    source_state: str | None,
    checkpoint_name: str = "default",
    cursor: str | None = None,
    last_external_id: str | None = None,
    last_ingestion_run_id=None,
    completed: bool = False,
    metadata: dict | None = None,
) -> IngestionCheckpoint:
    checkpoint = load_ingestion_checkpoint(
        session,
        source_name=source_name,
        source_state=source_state,
        checkpoint_name=checkpoint_name,
    )
    if checkpoint is None:
        checkpoint = IngestionCheckpoint(
            source_name=source_name,
            source_state=source_state,
            checkpoint_name=checkpoint_name,
        )
    checkpoint.cursor = cursor
    checkpoint.last_external_id = last_external_id
    checkpoint.last_ingestion_run_id = last_ingestion_run_id
    checkpoint.completed_at = datetime.now(timezone.utc) if completed else None
    checkpoint.details = metadata or {}
    session.add(checkpoint)
    session.commit()
    session.refresh(checkpoint)
    return checkpoint


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


def address_to_read(
    address: Address,
    supporting_information: AddressSupportingInformationRead | None = None,
) -> AddressRead:
    return AddressRead(
        id=address.id,
        line1=address.line1,
        line2=address.line2,
        city=address.city,
        state=address.state,
        postal_code=address.postal_code,
        county=address.county,
        latitude=address.latitude,
        longitude=address.longitude,
        address_precision=address.address_precision,
        supporting_information=supporting_information or AddressSupportingInformationRead(),
    )


def registrant_to_detail(session: Session, row: Registrant) -> RegistrantDetail:
    address_rows = session.exec(
        select(Address)
        .options(
            load_only(
                Address.id,
                Address.line1,
                Address.line2,
                Address.city,
                Address.state,
                Address.postal_code,
                Address.county,
                Address.latitude,
                Address.longitude,
                Address.address_precision,
            )
        )
        .where(Address.registrant_id == row.id)
    ).all()

    return RegistrantDetail(
        id=row.id,
        external_id=row.external_id,
        full_name=row.full_name,
        risk_level=row.risk_level,
        last_seen=row.last_seen,
        date_of_birth=row.date_of_birth,
        race=row.race,
        sex=row.sex,
        addresses=[address_to_read(address, load_address_supporting_information(session, address.id)) for address in address_rows],
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


def get_registrant(session: Session, registrant_id: UUID | str) -> RegistrantDetail | None:
    try:
        lookup_id = UUID(str(registrant_id))
    except ValueError:
        return None

    row = session.get(Registrant, lookup_id)
    if row is None:
        return None
    return registrant_to_detail(session, row)


def list_sources(session: Session | None = None) -> list[SourceSummary]:
    connectors_by_state = {connector.state: connector for connector in list_connectors() if connector.state}
    connectors_by_name = {connector.name: connector for connector in list_connectors()}

    if session is None:
        return [
            SourceSummary(
                name=connector.name,
                state=connector.state,
                enabled=True,
                supports_fetch=True,
                notes="Skeleton connector only. Implement gentle, compliant ingestion per source.",
            )
            for connector in connectors_by_state.values()
        ]

    rows = session.exec(select(RegistrySource).order_by(RegistrySource.state)).all()
    if not rows:
        return list_sources()

    return [
        SourceSummary(
            name=(
                connectors_by_state.get(row.state).name
                if connectors_by_state.get(row.state)
                else row.state.lower().replace(" ", "-")
            ),
            state=row.state,
            enabled=True,
            supports_fetch=row.state in connectors_by_state or row.state.lower().replace(" ", "-") in connectors_by_name,
            notes=row.notes or "State registry metadata imported from the national source directory.",
            official_registry_url=row.official_registry_url,
            access_surface=row.access_surface,
            recommended_acquisition_path=row.recommended_acquisition_path,
            jurisdiction_type=row.jurisdiction_type,
            state_code=row.state_code,
            registry_http_status=row.registry_http_status,
            final_registry_url=row.final_registry_url,
            registry_host=row.registry_host,
            registry_page_title=row.registry_page_title,
            registry_content_type=row.registry_content_type,
            vendor_name=row.vendor_name,
            robots_txt_url=row.robots_txt_url,
            robots_txt_status=row.robots_txt_status,
            metadata_retrieved_at=row.metadata_retrieved_at,
            metadata_error=row.metadata_error,
        )
        for row in rows
    ]


async def ingest_source(
    session: Session,
    source: str,
    *,
    dry_run: bool = True,
    limit: int | None = None,
    batch_size: int | None = None,
) -> IngestionRun:
    connector = get_connector(source)
    run = IngestionRun(
        source_name=connector.name,
        source_state=connector.state,
        status="running",
        notes="Batch ingestion run with resumable checkpoints.",
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    checkpoint = load_ingestion_checkpoint(
        session,
        source_name=connector.name,
        source_state=connector.state,
    )
    last_external_id = checkpoint.last_external_id if checkpoint else None
    batch_index = 0
    resume_cursor = checkpoint.cursor if checkpoint else None

    async for raw_payloads, next_cursor in connector.fetch_batches(
        limit=limit,
        batch_size=batch_size,
        cursor=resume_cursor,
    ):
        if not raw_payloads:
            continue
        batch_index += 1
        parsed = connector.parse(raw_payloads)
        normalized = connector.normalize(parsed)
        result = connector.upsert(
            session,
            normalized,
            dry_run=dry_run,
            ingestion_run_id=run.id,
        )
        if normalized:
            last_external_id = normalized[-1].get("external_id", last_external_id)
        checkpoint_metadata = {
            "batch_index": batch_index,
            "records_in_batch": len(raw_payloads),
            "records_seen": result.get("records_seen", len(normalized)),
            "dry_run": dry_run,
        }
        save_ingestion_checkpoint(
            session,
            source_name=connector.name,
            source_state=connector.state,
            cursor=next_cursor,
            last_external_id=last_external_id,
            last_ingestion_run_id=run.id,
            completed=next_cursor is None,
            metadata=checkpoint_metadata,
        )

    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    run.notes = f"Completed {batch_index} batch(s); last checkpoint {last_external_id or 'n/a'}."
    session.add(run)
    session.commit()
    session.refresh(run)
    return run
