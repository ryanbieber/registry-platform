from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlmodel import Session


class SourceConnector(ABC):
    name: str
    state: str | None = None
    source_url: str | None = None

    @abstractmethod
    async def fetch(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        """Fetch raw source payloads while respecting robots.txt and rate limits."""

    @abstractmethod
    def parse(self, raw_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert raw payloads into parsed intermediary records."""

    @abstractmethod
    def normalize(self, parsed_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Map parsed records into the platform's canonical schema."""

    @abstractmethod
    def upsert(
        self,
        session: Session,
        normalized_records: list[dict[str, Any]],
        *,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Persist records and raw payload references without aggressive scraping behavior."""
