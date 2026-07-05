from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin

import httpx

from registry.sources.base import SourceConnector


def _compact_text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _parse_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = _compact_text(value)
    if not text:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    text = _compact_text(value)
    if not text:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _compact_text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


class SouthDakotaRegistryConnector(SourceConnector):
    name = "south-dakota"
    state = "SD"
    source_url = "https://sor.sd.gov/Home/Search?d=t"
    _search_url = "https://sor.sd.gov/Offenders/Search"
    _cached_records: list[dict[str, Any]] | None = None

    async def _fetch_full_registry(self) -> dict[str, Any]:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=20.0), verify=False, headers=headers) as client:
            await client.get(self.source_url)
            response = await client.post(
                self._search_url,
                content=b"{}",
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "X-Requested-With": "XMLHttpRequest",
                    "Origin": "https://sor.sd.gov",
                    "Referer": self.source_url,
                },
            )
            response.raise_for_status()
            return response.json()

    async def _records(self) -> list[dict[str, Any]]:
        if self._cached_records is not None:
            return self._cached_records

        payload = await self._fetch_full_registry()
        records = payload.get("Results") or []
        self._cached_records = records
        return records

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
        records = await self._records()
        start = int(cursor) if cursor else 0
        if start < 0:
            start = 0

        selected = records[start:]
        if limit is not None:
            selected = selected[:limit]
        if not selected:
            return

        batch_limit = batch_size or 500
        for offset in range(0, len(selected), batch_limit):
            batch = selected[offset : offset + batch_limit]
            next_index = start + offset + len(batch)
            next_cursor = str(next_index) if next_index < start + len(selected) else None
            yield batch, next_cursor

    def parse(self, raw_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return raw_payloads

    def normalize(self, parsed_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for record in parsed_records:
            offender_id = record.get("Id")
            if offender_id is None:
                continue

            image_file = _compact_text(record.get("ImageFileName"))
            image_url = urljoin(self.source_url, f"/sorfiles/OffenderImages/{image_file}") if image_file else None

            normalized.append(
                {
                    "external_id": f"sd:{offender_id}",
                    "full_name": _compact_text(record.get("FullName"))
                    or " ".join(
                        part for part in [_compact_text(record.get("LastName")), _compact_text(record.get("FirstName"))] if part
                    ).strip(),
                    "date_of_birth": _parse_date(record.get("DateOfBirth")),
                    "demographics": {
                        "county": _compact_text(record.get("County")) or None,
                        "is_in_jail": record.get("IsInJail"),
                        "registration_ori": _compact_text(record.get("Ori")) or None,
                        "image_file": image_file,
                        "image_date": _parse_date(record.get("ImageDate")),
                    },
                    "aliases": [],
                    "addresses": [
                        {
                            "line1": _compact_text(record.get("Address")) or None,
                            "city": _compact_text(record.get("City")) or None,
                            "state": "SD",
                            "postal_code": _compact_text(record.get("ZipCode")) or None,
                            "county": _compact_text(record.get("County")) or None,
                            "latitude": _to_float(record.get("Latitude")),
                            "longitude": _to_float(record.get("Longitude")),
                            "address_precision": "registry",
                        }
                    ]
                    if any(
                        [
                            _compact_text(record.get("Address")),
                            _compact_text(record.get("City")),
                            _compact_text(record.get("ZipCode")),
                            _compact_text(record.get("County")),
                        ]
                    )
                    else [],
                    "offenses": [],
                    "photos": (
                        [
                            {
                                "image_url": image_url,
                                "captured_at": _parse_datetime(record.get("ImageDate")),
                            }
                        ]
                        if image_url
                        else []
                    ),
                    "source_url": self.source_url,
                    "raw_payload": record,
                }
            )
        return normalized
