from fastapi import APIRouter, Depends
from sqlmodel import Session

from registry.db import get_session
from registry.schemas import IngestRequest, IngestionRunRead
from registry.services import ingest_source

router = APIRouter(tags=["ingestion"])


@router.post("/ingest/{source}", response_model=IngestionRunRead)
async def ingest(source: str, request: IngestRequest, session: Session = Depends(get_session)) -> IngestionRunRead:
    run = await ingest_source(session, source, dry_run=request.dry_run, limit=request.limit)
    return IngestionRunRead.model_validate(run, from_attributes=True)
