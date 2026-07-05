from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any, AsyncIterator

from registry.sources.base import SourceConnector


class FloridaRegistryCsvConnector(SourceConnector):
    name = "florida"
    state = "FL"
    source_url = "https://offender.fdle.state.fl.us/offender/publicDataFile.jsf"
    csv_env_var = "REGISTRY_FLORIDA_DOWNLOAD_CSV"

    @classmethod
    def is_configured(cls) -> bool:
        path = os.environ.get(cls.csv_env_var)
        return bool(path and Path(path).expanduser().exists())

    def _csv_path(self) -> Path:
        raw_path = os.environ.get(self.csv_env_var)
        if not raw_path:
            raise FileNotFoundError(
                f"{self.csv_env_var} is not set. Download the Florida registry CSV and point this env var at it."
            )
        path = Path(raw_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Florida registry CSV not found at {path}")
        return path

    async def fetch(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        async for batch, _cursor in self.fetch_batches(limit=limit):
            records.extend(batch)
        return records

    async def fetch_batches(
        self,
        *,
        limit: int | None = None,
        batch_size: int | None = None,
        cursor: str | None = None,
    ) -> AsyncIterator[tuple[list[dict[str, Any]], str | None]]:
        path = self._csv_path()
        start_index = int(cursor) if cursor else 0
        emitted = 0
        batch: list[dict[str, Any]] = []
        batch_limit = batch_size or 500

        with path.open(newline="", encoding="utf-8-sig") as file_handle:
            reader = csv.DictReader(file_handle)
            for row_index, row in enumerate(reader):
                if row_index < start_index:
                    continue
                batch.append(row)
                emitted += 1
                if limit is not None and emitted >= limit:
                    yield batch, None
                    return
                if len(batch) >= batch_limit:
                    yield batch, str(row_index + 1)
                    batch = []

        if batch:
            yield batch, None

    def parse(self, raw_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return raw_payloads

    def normalize(self, parsed_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for index, row in enumerate(parsed_records, start=1):
            lowered = {key.strip().lower(): value for key, value in row.items()}
            external_id = (
                lowered.get("id")
                or lowered.get("offender_id")
                or lowered.get("registry_id")
                or lowered.get("person_id")
                or lowered.get("case_number")
                or lowered.get("doc_id")
                or f"florida:{index}"
            )
            first_name = lowered.get("first_name") or lowered.get("firstname")
            last_name = lowered.get("last_name") or lowered.get("lastname")
            full_name = lowered.get("full_name") or lowered.get("name") or " ".join(
                part for part in [first_name, last_name] if part
            )
            county = lowered.get("county") or lowered.get("county_name")
            city = lowered.get("city") or lowered.get("city_name")
            postal_code = lowered.get("zip") or lowered.get("zipcode") or lowered.get("postal_code")
            line1 = lowered.get("address") or lowered.get("street_address") or lowered.get("residence_address")
            offense_name = lowered.get("offense") or lowered.get("offense_name") or lowered.get("charge")
            statute = lowered.get("statute") or lowered.get("statute_number")

            normalized.append(
                {
                    "external_id": str(external_id).strip(),
                    "full_name": str(full_name).strip() or str(external_id).strip(),
                    "risk_level": lowered.get("risk_level") or lowered.get("tier") or lowered.get("status"),
                    "date_of_birth": lowered.get("date_of_birth") or lowered.get("dob"),
                    "source_url": self.source_url,
                    "raw_payload": row,
                    "addresses": [
                        {
                            "line1": line1,
                            "city": city,
                            "state": "FL",
                            "postal_code": postal_code,
                            "county": county,
                        }
                    ]
                    if any([line1, city, county, postal_code])
                    else [],
                    "offenses": [
                        {
                            "offense_name": offense_name or "Registry offense",
                            "statute": statute,
                            "offense_date": lowered.get("offense_date") or lowered.get("conviction_date"),
                        }
                    ]
                    if offense_name or statute
                    else [],
                }
            )
        return normalized
