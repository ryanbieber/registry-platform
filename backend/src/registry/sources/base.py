from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from sqlmodel import Session

from registry.sources.persistence import persist_normalized_records


class SourceConnector(ABC):
    name: str
    state: str | None = None
    source_url: str | None = None

    @abstractmethod
    async def fetch(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        """Fetch raw source payloads while respecting robots.txt and rate limits."""

    async def fetch_batches(
        self,
        *,
        limit: int | None = None,
        batch_size: int | None = None,
        cursor: str | None = None,
    ) -> AsyncIterator[tuple[list[dict[str, Any]], str | None]]:
        """Yield batches of raw source payloads and an optional resume cursor."""
        yield await self.fetch(limit=limit), None

    @abstractmethod
    def parse(self, raw_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert raw payloads into parsed intermediary records."""

    @abstractmethod
    def normalize(self, parsed_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Map parsed records into the platform's canonical schema."""

    def upsert(
        self,
        session: Session,
        normalized_records: list[dict[str, Any]],
        *,
        dry_run: bool = True,
        ingestion_run_id: Any | None = None,
    ) -> dict[str, Any]:
        """Persist records and raw payload references without aggressive scraping behavior."""
        if not normalized_records:
            return {"source": self.name, "state": self.state, "dry_run": dry_run, "records_seen": 0}

        if ingestion_run_id is None and not dry_run:
            raise ValueError("ingestion_run_id is required for non-dry-run upserts")

        return persist_normalized_records(
            session,
            source_name=self.name,
            source_state=self.state,
            ingestion_run_id=ingestion_run_id,
            normalized_records=normalized_records,
            dry_run=dry_run,
        )
