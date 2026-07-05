from typing import Any

from registry.sources.base import SourceConnector


class CaliforniaStubConnector(SourceConnector):
    name = "california"
    state = "CA"
    source_url = "https://www.meganslaw.ca.gov/"

    async def fetch(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        return [
            {
                "source_url": self.source_url,
                "external_id": "stub-ca-001",
                "note": "Stub payload only. No live scraping is implemented.",
                "limit": limit,
            }
        ]

    def parse(self, raw_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return raw_payloads

    def normalize(self, parsed_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "external_id": record["external_id"],
                "full_name": "Example Person",
                "risk_level": None,
                "source_url": record["source_url"],
                "raw_payload": record,
            }
            for record in parsed_records
        ]
