from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from registry.sources.base import SourceConnector


def _format_full_name(record: dict[str, Any]) -> str:
    display_name = (record.get("display_name") or "").strip()
    if display_name:
        return display_name
    parts = [
        record.get("last_name"),
        record.get("first_name"),
        record.get("middle_name"),
    ]
    return " ".join(part for part in parts if part).strip()


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _inches_to_cm(value: Any) -> int | None:
    inches = _to_float(value)
    if inches is None:
        return None
    return round(inches * 2.54)


def _pounds_to_kg(value: Any) -> int | None:
    pounds = _to_float(value)
    if pounds is None:
        return None
    return round(pounds * 0.45359237)


class IowaRegistryApiConnector(SourceConnector):
    name = "iowa"
    state = "IA"
    source_url = "https://www.iowasexoffender.gov/api/search/results.json"
    page_size_cap = 25

    async def _fetch_page(
        self,
        *,
        page: int,
        per_page: int,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = {"page": page, "per_page": per_page}
        if params:
            query.update(params)
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=10.0)) as client:
            response = await client.get(self.source_url, params=query, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            return response.json()

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
        per_page = min(batch_size or self.page_size_cap, self.page_size_cap)
        page = int(cursor) if cursor else 1
        remaining = limit

        while True:
            payload = await self._fetch_page(page=page, per_page=per_page)
            raw_records = payload.get("records") or []
            if remaining is not None:
                raw_records = raw_records[:remaining]
            if not raw_records:
                return

            next_cursor = None
            if payload.get("pages") and page < int(payload["pages"]) and (remaining is None or len(raw_records) == per_page):
                next_cursor = str(page + 1)
            yield raw_records, next_cursor

            if remaining is not None:
                remaining -= len(raw_records)
                if remaining <= 0:
                    return

            if next_cursor is None:
                return
            page += 1

    def parse(self, raw_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return raw_payloads

    def normalize(self, parsed_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for record in parsed_records:
            external_id = str(record.get("registrant") or record.get("oci") or "").strip()
            if not external_id:
                continue

            alias_records = record.get("aliases") or []
            photo_urls = record.get("photos") or []
            convictions = record.get("convictions") or []

            aliases = []
            for alias in alias_records:
                alias_name = " ".join(
                    part for part in [alias.get("last_name"), alias.get("first_name"), alias.get("middle_name")] if part
                ).strip()
                if alias_name:
                    aliases.append(alias_name)

            offense_rows = []
            for conviction in convictions:
                victims = conviction.get("victims") or []
                offense_rows.append(
                    {
                        "offense_name": conviction.get("conviction") or "Iowa registry offense",
                        "offense_date": conviction.get("conviction_date") or None,
                        "statute": conviction.get("iowa_code") or None,
                        "victim_age": ", ".join(
                            sorted({victim.get("age") for victim in victims if victim.get("age")})
                        )
                        or None,
                        "victim_gender": ", ".join(
                            sorted({victim.get("gender") for victim in victims if victim.get("gender")})
                        )
                        or None,
                    }
                )

            normalized.append(
                {
                    "external_id": external_id,
                    "full_name": _format_full_name(record),
                    "date_of_birth": record.get("birthdate") or None,
                    "race": record.get("race") or None,
                    "sex": record.get("gender") or None,
                    "height_cm": _inches_to_cm(record.get("height_inches")),
                    "weight_kg": _pounds_to_kg(record.get("weight_pounds")),
                    "eye_color": record.get("eye_color") or None,
                    "hair_color": record.get("hair_color") or None,
                    "risk_level": record.get("tier") or None,
                    "demographics": {
                        "oci": record.get("oci"),
                        "county": record.get("county") or None,
                        "skin_tone": record.get("skin_tone") or None,
                        "residency_restriction": record.get("residency_restriction") or None,
                        "employment_restriction": record.get("employment_restriction") or None,
                        "exclusion_zones": record.get("exclusion_zones") or None,
                        "victim_minors": _to_int(record.get("victim_minors")),
                        "victim_adults": _to_int(record.get("victim_adults")),
                        "victim_unknown": _to_int(record.get("victim_unknown")),
                        "registrant_cluster": _to_int(record.get("registrant_cluster")),
                        "wanted": record.get("wanted") or None,
                        "distance": record.get("distance") or None,
                        "last_changed": record.get("last_changed") or None,
                    },
                    "aliases": aliases,
                    "addresses": [
                        {
                            "line1": record.get("line_1") or None,
                            "line2": record.get("line_2") or None,
                            "city": record.get("city") or None,
                            "state": "IA",
                            "postal_code": record.get("postal_code") or None,
                            "county": record.get("county") or None,
                            "latitude": _to_float(record.get("lat")),
                            "longitude": _to_float(record.get("lon")),
                            "address_precision": "registry",
                        }
                    ]
                    if any([record.get("line_1"), record.get("city"), record.get("postal_code"), record.get("county")])
                    else [],
                    "offenses": offense_rows,
                    "photos": [{"image_url": url} for url in photo_urls if url],
                    "source_url": self.source_url,
                    "raw_payload": record,
                }
            )
        return normalized
