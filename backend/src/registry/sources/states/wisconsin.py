from __future__ import annotations

import asyncio
import re
import string
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin

import httpx

from registry.sources.base import SourceConnector

_ALPHABET = string.ascii_uppercase
_MAX_RESULTS_PER_QUERY = 240


class _SearchTooBroad(RuntimeError):
    pass


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
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
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
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
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


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = _compact_text(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _parse_height_cm(value: Any) -> int | None:
    text = _compact_text(value)
    if not text:
        return None
    match = re.search(r"(?P<feet>\d+)\s*'\s*(?P<inches>\d{1,2})", text)
    if not match:
        return None
    inches = int(match.group("feet")) * 12 + int(match.group("inches"))
    return round(inches * 2.54)


def _parse_weight_kg(value: Any) -> int | None:
    text = _compact_text(value)
    if not text:
        return None
    match = re.search(r"(?P<weight>\d+)", text)
    if not match:
        return None
    return round(int(match.group("weight")) * 0.453592)


def _normalize_address(
    payload: dict[str, Any] | None,
    *,
    address_precision: str = "registry",
) -> dict[str, Any] | None:
    if not payload:
        return None

    line1 = _compact_text(payload.get("street") or payload.get("street1"))
    line2 = _compact_text(payload.get("street2"))
    city = _compact_text(payload.get("city"))
    state = _compact_text(payload.get("state"))
    postal_code = _compact_text(payload.get("zip") or payload.get("postalCode") or payload.get("postal_code"))
    county = _compact_text(payload.get("county"))
    latitude = _to_float(payload.get("latitude") or payload.get("lat"))
    longitude = _to_float(payload.get("longitude") or payload.get("lon"))

    street3 = _compact_text(payload.get("street3"))
    if street3 and not city:
        city_match = re.match(r"^(?P<city>.+?),\s*(?P<state>[A-Z]{2})\s+(?P<postal>[\w\- ]+)$", street3)
        if city_match:
            city = _compact_text(city_match.group("city"))
            state = _compact_text(city_match.group("state")) or state
            postal_code = _compact_text(city_match.group("postal")) or postal_code

    if not any([line1, line2, city, state, postal_code, county, latitude, longitude]):
        return None

    return {
        "line1": line1,
        "line2": line2,
        "city": city,
        "state": state or "WI",
        "postal_code": postal_code,
        "county": county,
        "latitude": latitude,
        "longitude": longitude,
        "address_precision": address_precision,
    }


class WisconsinRegistryConnector(SourceConnector):
    name = "wisconsin"
    state = "WI"
    source_url = "https://sort.doc.state.wi.us/name-search"
    _api_base = "https://sort.doc.state.wi.us/api/"
    _image_base = "https://sort.doc.state.wi.us/api/image"

    async def _fetch_name_search(
        self,
        client: httpx.AsyncClient,
        *,
        last: str,
        first: str | None = None,
        middle: str | None = None,
    ) -> list[dict[str, Any]]:
        body: dict[str, Any] = {"last": last}
        if first:
            body["first"] = first
        if middle:
            body["middle"] = middle

        response = await client.post(
            urljoin(self._api_base, "name-search"),
            json=body,
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        )
        try:
            payload = response.json()
        except Exception:  # pragma: no cover - defensive
            payload = {}

        if response.status_code == 200:
            data = payload.get("data")
            return data if isinstance(data, list) else []

        error_info = payload.get("errorInfo") or {}
        error_status = _compact_text(error_info.get("errorStatus")) or ""
        if response.status_code == 404 and error_status == "Data not found.":
            return []
        if "more than 240 results" in error_status.lower():
            raise _SearchTooBroad(error_status)
        raise RuntimeError(error_status or f"Wisconsin name search failed with HTTP {response.status_code}")

    async def _fetch_offender_detail(self, client: httpx.AsyncClient, offender_id: str) -> dict[str, Any]:
        response = await client.post(
            urljoin(self._api_base, f"offenderdetails/{offender_id}"),
            json={},
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        )
        if response.status_code != 200:
            return {}
        try:
            payload = response.json()
        except Exception:  # pragma: no cover - defensive
            return {}
        detail = payload.get("data")
        return detail if isinstance(detail, dict) else {}

    def _merge_record(self, search_result: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
        merged = {**search_result, **detail}
        merged["search_result"] = search_result
        return merged

    async def _walk_last_prefixes(
        self,
        client: httpx.AsyncClient,
        *,
        prefix: str,
        seen: set[str],
        depth: int = 0,
    ) -> AsyncIterator[dict[str, Any]]:
        try:
            results = await self._fetch_name_search(client, last=prefix)
        except _SearchTooBroad:
            results = None

        if results is None or len(results) >= _MAX_RESULTS_PER_QUERY:
            if depth >= 8:
                return
            for letter in _ALPHABET:
                async for record in self._walk_last_prefixes(
                    client,
                    prefix=f"{prefix}{letter}",
                    seen=seen,
                    depth=depth + 1,
                ):
                    yield record
            return

        if not results:
            return

        unique_results: list[dict[str, Any]] = []
        offender_ids: list[str] = []
        for search_result in results:
            offender_id = _compact_text(search_result.get("id") or search_result.get("offenderId"))
            if not offender_id or offender_id in seen:
                continue
            seen.add(offender_id)
            unique_results.append(search_result)
            offender_ids.append(offender_id)

        if not unique_results:
            return

        detail_payloads = await asyncio.gather(
            *(self._fetch_offender_detail(client, offender_id) for offender_id in offender_ids)
        )
        for search_result, detail in zip(unique_results, detail_payloads, strict=False):
            yield self._merge_record(search_result, detail)

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
        del cursor
        batch_limit = batch_size or 100
        batch: list[dict[str, Any]] = []
        seen = 0
        seen_ids: set[str] = set()

        headers = {"User-Agent": "Mozilla/5.0"}
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=20.0),
            verify=False,
            headers=headers,
        ) as client:
            for letter in _ALPHABET:
                async for record in self._walk_last_prefixes(client, prefix=letter, seen=seen_ids):
                    batch.append(record)
                    seen += 1
                    if len(batch) >= batch_limit:
                        yield batch, None
                        batch = []
                    if limit is not None and seen >= limit:
                        if batch:
                            yield batch, None
                        return

        if batch:
            yield batch, None

    def parse(self, raw_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return raw_payloads

    def normalize(self, parsed_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for record in parsed_records:
            offender_id = _compact_text(record.get("offenderId") or record.get("id"))
            if not offender_id:
                continue

            primary = (
                record.get("primary")
                if isinstance(record.get("primary"), dict)
                else record.get("primaryResidence")
                if isinstance(record.get("primaryResidence"), dict)
                else {}
            )
            other_address_info = record.get("otherAddress") if isinstance(record.get("otherAddress"), dict) else {}
            other_address = other_address_info.get("address") or {}

            primary_address = _normalize_address(primary)
            other_registry_address = _normalize_address(other_address, address_precision="registry-office")

            addresses = [address for address in [primary_address, other_registry_address] if address]

            aliases = [
                alias
                for alias in (_compact_text(alias) for alias in (record.get("aliases") or []))
                if alias
            ]
            photo_id = _compact_text(record.get("photoId"))
            located = "true" if primary_address and primary_address.get("latitude") is not None and primary_address.get("longitude") is not None else "false"
            photo_taken = _parse_datetime(record.get("photoTaken"))
            photo_url = f"{self._image_base}?photoId={photo_id}&located={located}" if photo_id else None

            offenses = []
            for offense in record.get("offenses") or []:
                if not isinstance(offense, dict):
                    continue
                offense_name = _compact_text(offense.get("offenseText")) or "Wisconsin registry offense"
                offenses.append(
                    {
                        "offense_name": offense_name,
                        "conviction_date": _parse_date(offense.get("convictionDate")),
                        "statute": _compact_text(offense.get("offenseCode")),
                    }
                )

            normalized.append(
                {
                    "external_id": f"wi:{offender_id}",
                    "full_name": _compact_text(record.get("fullName")) or f"Wisconsin offender {offender_id}",
                    "risk_level": _compact_text(record.get("registrationTerm"))
                    or _compact_text(record.get("complianceStatus")),
                    "sex": _compact_text(record.get("gender")),
                    "race": _compact_text(record.get("race")),
                    "ethnicity": _compact_text(record.get("ethnicity")),
                    "height_cm": _parse_height_cm(record.get("height")),
                    "weight_kg": _parse_weight_kg(record.get("weight")),
                    "eye_color": _compact_text(record.get("eyeColor")),
                    "hair_color": _compact_text(record.get("hairColor")),
                    "demographics": {
                        "doc_num": _compact_text(record.get("docNum")),
                        "offender_id": offender_id,
                        "age": _to_int(record.get("age")),
                        "compliance_status": _compact_text(record.get("complianceStatus")),
                        "supervision_status": _compact_text(record.get("supervisionStatus")),
                        "registration_start": _parse_date(record.get("registrationStart")),
                        "registration_end": _parse_date(record.get("registrationEnd")),
                        "registration_term": _compact_text(record.get("registrationTerm")),
                        "photo_taken": photo_taken.isoformat() if photo_taken else None,
                        "verified_note": _compact_text(record.get("verifiedNote")),
                        "mail_response": _compact_text(record.get("mailResponse")),
                        "primary_county": _compact_text(primary.get("county")),
                        "primary_latitude": _to_float(primary.get("latitude")),
                        "primary_longitude": _to_float(primary.get("longitude")),
                        "supervising_office": {
                            "label": _compact_text(other_address_info.get("label")) if other_address_info else None,
                            "name": _compact_text(other_address_info.get("name")) if other_address_info else None,
                            "phone": _compact_text(other_address.get("phone")) if other_address else None,
                        },
                    },
                    "aliases": aliases,
                    "addresses": addresses,
                    "offenses": offenses,
                    "photos": (
                        [
                            {
                                "image_url": photo_url,
                                "captured_at": _parse_datetime(record.get("photoTaken")),
                            }
                        ]
                        if photo_url
                        else []
                    ),
                    "source_url": self.source_url,
                    "raw_payload": record,
                }
            )
        return normalized
