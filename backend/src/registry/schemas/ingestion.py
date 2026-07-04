from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class IngestRequest(BaseModel):
    dry_run: bool = True
    limit: Optional[int] = None


class IngestionRunRead(BaseModel):
    id: UUID
    source_name: str
    source_state: Optional[str] = None
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None


class SourceSummary(BaseModel):
    name: str
    state: Optional[str] = None
    enabled: bool
    supports_fetch: bool
    notes: str
