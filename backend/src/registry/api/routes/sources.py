from fastapi import APIRouter, Depends
from sqlmodel import Session

from registry.db import get_session
from registry.schemas import SourceSummary
from registry.services import list_sources

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=list[SourceSummary])
def sources(session: Session = Depends(get_session)) -> list[SourceSummary]:
    return list_sources(session)
