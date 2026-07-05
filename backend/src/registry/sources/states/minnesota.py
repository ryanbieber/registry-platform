from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from registry.sources.base import SourceConnector


def _compact_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = " ".join(value.split())
    return text or None


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


def _parse_date(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("/Date(") and text.endswith(")/"):
        try:
            return datetime.fromtimestamp(int(text[6:-2]) / 1000, tz=timezone.utc).date()
        except ValueError:
            return None
    for fmt in ("%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_block_text(block) -> list[str]:
    lines = []
    for text in block.stripped_strings:
        compact = _compact_text(text)
        if compact:
            lines.append(compact)
    return lines


def _parse_address(lines: list[str]) -> dict[str, Any]:
    if not lines:
        return {}

    city = state = postal_code = None
    line1 = lines[0]
    line2 = None

    city_match = re.match(r"^(?P<city>.+?),\s*(?P<state>[A-Za-z]{2})\s+(?P<postal>\d{5}(?:-\d{4})?)$", lines[-1])
    if city_match:
        city = city_match.group("city")
        state = city_match.group("state")
        postal_code = city_match.group("postal")

    address_lines = lines[:-1] if city_match else lines
    if len(address_lines) >= 2:
        line1 = address_lines[0]
        line2 = " ".join(address_lines[1:]) if len(address_lines) > 2 else address_lines[1]

    return {
        "line1": line1,
        "line2": line2,
        "city": city,
        "state": state,
        "postal_code": postal_code,
    }


class MinnesotaRegistryConnector(SourceConnector):
    name = "minnesota"
    state = "MN"
    source_url = "https://coms.doc.state.mn.us/PublicRegistrantSearch"
    page_size_cap = 100

    async def _fetch_group_results(self, client: httpx.AsyncClient, group: int) -> list[dict[str, Any]]:
        response = await client.get(
            f"{self.source_url}/Results/GetSearchResults",
            params={"Group": group},
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        return response.json()

    async def _fetch_detail_html(self, client: httpx.AsyncClient, offender_id: int, *, group: int) -> str:
        response = await client.get(
            f"{self.source_url}/Details",
            params={
                "OID": offender_id,
                "City": "",
                "County": "",
                "CountyDesc": "",
                "Firstname": "",
                "LastName": "",
                "Zip": "",
                "Group": group,
            },
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        return response.text

    def _parse_detail_html(self, html: str) -> dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")
        detail: dict[str, Any] = {
            "aliases": [],
            "addresses": [],
            "offenses": [],
            "photos": [],
        }

        front = soup.find("img", alt=re.compile("Mugshot Front", re.I))
        side = soup.find("img", alt=re.compile("Mugshot Side", re.I))
        if front and front.get("src"):
            detail["photo_url"] = urljoin(f"{self.source_url}/", front["src"].replace("\\", "/"))
        if front and front.get("src"):
            detail["photos"].append({"image_url": urljoin(f"{self.source_url}/", front["src"].replace("\\", "/"))})
        if side and side.get("src"):
            detail["photos"].append({"image_url": urljoin(f"{self.source_url}/", side["src"].replace("\\", "/"))})

        for block in soup.find_all("div", class_="grayBorder"):
            label_el = block.select_one(".fixedWidthLabel .fontBold")
            value_el = block.select_one(".displayText")
            if not label_el or not value_el:
                continue
            label = _compact_text(label_el.get_text(" ", strip=True).rstrip(":")) or ""
            value_lines = _parse_block_text(value_el)
            value_text = _compact_text(value_el.get_text(" ", strip=True)) or ""

            if label == "Birth Date":
                detail["birthdate"] = value_text
            elif label == "Race/Ethnicity":
                detail["race_ethnicity"] = value_text
            elif label == "Skin Tone":
                detail["skin_tone"] = value_text
            elif label == "Hair Color":
                detail["hair_color"] = value_text
            elif label == "Eye Color":
                detail["eye_color"] = value_text
            elif label == "Height":
                detail["height"] = value_text
            elif label == "Weight":
                detail["weight"] = value_text
            elif label == "Build":
                detail["build"] = value_text
            elif label == "Release Date":
                detail["release_date"] = value_text
            elif label == "Offense Statute(s)":
                detail["offense_statutes"] = value_text
            elif label == "Offense Information":
                detail["offense_information"] = value_text
            elif label == "Address County":
                detail["address_county"] = value_text
            elif label == "Registered Address":
                detail["addresses"] = [
                    {
                        **_parse_address(value_lines),
                        "address_type": "registered",
                    }
                ] if value_lines else []
            elif label == "Law Enforcement Agency":
                detail["law_enforcement_agency"] = value_text
            elif label == "Also Known As Names":
                aliases = [line for line in value_lines if line]
                detail["aliases"] = aliases

        return detail

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
        remaining = limit
        start = int(cursor) if cursor else 0
        if start < 0:
            start = 0

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0), verify=False) as client:
            summaries: list[dict[str, Any]] = []
            for group in (10, 11):
                group_rows = await self._fetch_group_results(client, group)
                for row in group_rows:
                    row = dict(row)
                    row["group"] = group
                    summaries.append(row)

            seen_ids: set[int] = set()
            unique_summaries: list[dict[str, Any]] = []
            for row in summaries:
                offender_id = _to_int(row.get("id"))
                if offender_id is None or offender_id in seen_ids:
                    continue
                seen_ids.add(offender_id)
                unique_summaries.append(row)

            selected = unique_summaries[start:]
            if remaining is not None:
                selected = selected[:remaining]
            if not selected:
                return

            chunk_size = min(batch_size or self.page_size_cap, self.page_size_cap)
            for offset in range(0, len(selected), chunk_size):
                chunk = selected[offset : offset + chunk_size]
                detail_htmls = await asyncio.gather(
                    *(self._fetch_detail_html(client, _to_int(row["id"]) or 0, group=row["group"]) for row in chunk)
                )
                batch = [
                    {
                        "summary": row,
                        "detail": self._parse_detail_html(detail_html),
                        "source_url": self.source_url,
                    }
                    for row, detail_html in zip(chunk, detail_htmls, strict=False)
                ]
                next_index = start + offset + len(chunk)
                next_cursor = str(next_index) if next_index < len(unique_summaries) else None
                yield batch, next_cursor

                if remaining is not None:
                    remaining -= len(chunk)
                    if remaining <= 0:
                        return

    def parse(self, raw_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return raw_payloads

    def normalize(self, parsed_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for record in parsed_records:
            summary = record.get("summary") or {}
            detail = record.get("detail") or {}
            offender_id = _to_int(summary.get("id"))
            if offender_id is None:
                continue

            full_name = _compact_text(summary.get("OffenderName")) or str(offender_id)
            birthdate = _parse_date(detail.get("birthdate"))
            move_date = _parse_date(summary.get("MoveDate"))

            addresses = detail.get("addresses") or []
            if not addresses and detail.get("address_county"):
                addresses = [
                    {
                        "line1": None,
                        "line2": None,
                        "city": None,
                        "state": "MN",
                        "postal_code": None,
                        "county": detail.get("address_county"),
                        "address_type": "registered",
                    }
                ]

            offense_name = detail.get("offense_information") or detail.get("offense_statutes") or "Minnesota registry offense"
            offense: dict[str, Any] = {
                "offense_name": offense_name,
                "statute": detail.get("offense_statutes") or None,
                "offense_date": _parse_date(detail.get("release_date")),
                "details": detail.get("offense_information") or None,
            }

            normalized.append(
                {
                    "external_id": str(offender_id),
                    "full_name": full_name,
                    "date_of_birth": birthdate.isoformat() if birthdate else None,
                    "race": detail.get("race_ethnicity"),
                    "sex": None,
                    "hair_color": detail.get("hair_color"),
                    "eye_color": detail.get("eye_color"),
                    "demographics": {
                        "group": summary.get("group"),
                        "move_date": move_date.isoformat() if move_date else None,
                        "skin_tone": detail.get("skin_tone"),
                        "height": detail.get("height"),
                        "weight": detail.get("weight"),
                        "build": detail.get("build"),
                        "address_county": detail.get("address_county"),
                        "law_enforcement_agency": detail.get("law_enforcement_agency"),
                    },
                    "aliases": detail.get("aliases") or [],
                    "addresses": addresses,
                    "offenses": [offense],
                    "photos": detail.get("photos") or [],
                    "source_url": self.source_url,
                    "raw_payload": {
                        "summary": summary,
                        "detail": detail,
                    },
                }
            )
        return normalized
