from fastapi import APIRouter

from registry.schemas import SourceSummary
from registry.services import list_sources

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=list[SourceSummary])
def sources() -> list[SourceSummary]:
    return list_sources()
