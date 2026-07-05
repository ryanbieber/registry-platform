from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class IngestRequest(BaseModel):
    dry_run: bool = True
    limit: Optional[int] = None
    batch_size: Optional[int] = None


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
    official_registry_url: Optional[str] = None
    access_surface: Optional[str] = None
    recommended_acquisition_path: Optional[str] = None
    jurisdiction_type: Optional[str] = None
    state_code: Optional[str] = None
    registry_http_status: Optional[int] = None
    final_registry_url: Optional[str] = None
    registry_host: Optional[str] = None
    registry_page_title: Optional[str] = None
    registry_content_type: Optional[str] = None
    vendor_name: Optional[str] = None
    robots_txt_url: Optional[str] = None
    robots_txt_status: Optional[int] = None
    metadata_retrieved_at: Optional[datetime] = None
    metadata_error: Optional[str] = None
