from __future__ import annotations

import asyncio
from datetime import datetime
import re
from collections.abc import AsyncIterator
from typing import Any

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


def _parse_mdy_date(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_address_block(block) -> dict[str, Any]:
    strings = [_compact_text(text) for text in block.stripped_strings]
    strings = [text for text in strings if text]
    if not strings:
        return {}

    city = state = postal_code = None
    line1 = strings[0]
    line2 = None

    city_match = re.match(r"^(?P<city>.+?),\s*(?P<state>[A-Za-z ]+)\s+(?P<postal>\d{5}(?:-\d{4})?)$", strings[-1])
    if city_match:
        city = city_match.group("city")
        state = city_match.group("state")
        postal_code = city_match.group("postal")

    address_lines = strings[:-1] if city_match else strings
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


def _parse_table(table) -> list[dict[str, Any]]:
    if table is None:
        return []
    headers = [_compact_text(th.get_text(" ", strip=True)) or "" for th in table.find_all("th")]
    rows: list[dict[str, Any]] = []
    for tr in table.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in tr.find_all("td")]
        if not cells:
            continue
        rows.append(dict(zip(headers, cells, strict=False)))
    return rows


class MichiganRegistryConnector(SourceConnector):
    name = "michigan"
    state = "MI"
    search_url = "https://mspsor.com/Home/RegistrySearchAjax"
    detail_url = "https://mspsor.com/Home/OffenderDetails/{offender_id}"
    source_url = "https://mspsor.com/Home/RegistrySearch?searchtype=all"
    page_size_cap = 100

    async def _fetch_search_page(self, client: httpx.AsyncClient, *, start: int, length: int) -> dict[str, Any]:
        payload = {
            "draw": 1,
            "start": start,
            "length": length,
            "search": {"value": "", "regex": False},
            "order": [{"column": 2, "dir": "asc"}],
            "columns": [],
        }
        response = await client.post(
            f"{self.search_url}?searchtype=all",
            json=payload,
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        return response.json()

    async def _fetch_detail_html(self, client: httpx.AsyncClient, offender_id: str) -> str:
        response = await client.get(
            self.detail_url.format(offender_id=offender_id),
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
            "vehicles": [],
            "scars_markings": [],
        }

        photo = soup.find("img", alt=re.compile("Photo of offender", re.I))
        if photo and photo.get("src"):
            detail["photo_url"] = photo.get("src")

        summary_labels = {
            "Registration Number",
            "MDOC #",
            "Status",
            "Age",
            "Last Verification Date",
            "Compliance Status",
            "Sex",
            "Race",
            "Hair",
            "Height",
            "Weight",
            "Eyes",
        }
        for row in soup.find_all("div", class_="row"):
            cols = [
                column
                for column in row.find_all("div", recursive=False)
                if "col" in (column.get("class") or [])
            ]
            if len(cols) < 2:
                continue
            label_el, value_el = cols[0], cols[1]
            label = _compact_text(label_el.get_text(" ", strip=True).rstrip(":")) or ""
            if label not in summary_labels:
                continue
            value_text = _compact_text(value_el.get_text(" ", strip=True)) or ""
            if label == "Age":
                match = re.search(r"(?P<age>\d+)\s*\(DOB:\s*(?P<dob>\d{2}/\d{2}/\d{4})\s*\)", value_text)
                if match:
                    detail["age"] = _to_int(match.group("age"))
                    detail["birthdate"] = match.group("dob")
            elif label == "Registration Number":
                detail["registration_number"] = value_text
            elif label == "MDOC #":
                detail["mdoc_number"] = value_text
            elif label == "Status":
                detail["status"] = value_text
            elif label == "Last Verification Date":
                detail["last_verification_date"] = value_text
            elif label == "Compliance Status":
                detail["compliance_status"] = value_text
            elif label == "Sex":
                detail["sex"] = value_text
            elif label == "Race":
                detail["race"] = value_text
            elif label == "Hair":
                detail["hair_color"] = value_text
            elif label == "Height":
                detail["height"] = value_text
            elif label == "Weight":
                detail["weight"] = value_text
            elif label == "Eyes":
                detail["eye_color"] = value_text

        addresses_section = soup.find(id="addresses")
        if addresses_section is not None:
            for heading in addresses_section.find_all("h3"):
                title = _compact_text(heading.get_text(" ", strip=True))
                row = heading.find_next_sibling("div", class_="row")
                if row is None:
                    continue
                block = row.find("div", class_="col")
                if block is None:
                    continue
                address = _parse_address_block(block)
                if not any(address.values()):
                    continue
                address["address_type"] = title
                detail["addresses"].append(address)

        aliases_section = soup.find(id="aliases")
        if aliases_section is not None:
            detail["aliases"] = [
                _compact_text(li.get_text(" ", strip=True))
                for li in aliases_section.find_all("li")
                if _compact_text(li.get_text(" ", strip=True))
            ]

        offenses_section = soup.find(id="offenses")
        if offenses_section is not None:
            for card in offenses_section.select("div.card"):
                header = card.find("div", class_="card-header")
                header_text = _compact_text(header.get_text(" ", strip=True)) if header else None
                if not header_text:
                    continue
                statute, offense_name = (header_text.split(" - ", 1) + [None])[:2] if " - " in header_text else (None, header_text)
                offense: dict[str, Any] = {
                    "offense_name": offense_name or header_text,
                    "statute": statute,
                }
                for row in card.find_all("div", class_="row"):
                    label_el = row.select_one("div.col.text-right")
                    value_el = row.select_one("div.col.font-weight-bold")
                    if not label_el or not value_el:
                        continue
                    label = _compact_text(label_el.get_text(" ", strip=True).rstrip(":")) or ""
                    value = _compact_text(value_el.get_text(" ", strip=True))
                    if not value:
                        continue
                    if label == "Date Convicted":
                        offense["conviction_date"] = value
                    elif label == "Conviction State":
                        offense["conviction_state"] = value
                    elif label == "County":
                        offense["county"] = value
                    elif label == "Court":
                        offense["court"] = value
                    elif label == "Counts":
                        offense["counts"] = value
                    elif label == "Attempted":
                        offense["attempted"] = value
                    elif label == "Details":
                        offense["details"] = value
                detail["offenses"].append(offense)

        scars_section = soup.find(id="scarsmarkstattoos")
        if scars_section is not None:
            section_text = _compact_text(scars_section.get_text(" ", strip=True)) or ""
            if section_text and "None Found" not in section_text:
                scar_items = [
                    _compact_text(li.get_text(" ", strip=True))
                    for li in scars_section.find_all("li")
                    if _compact_text(li.get_text(" ", strip=True))
                ]
                if scar_items:
                    detail["scars_markings"] = scar_items
                else:
                    table = scars_section.find("table")
                    detail["scars_markings"] = [
                        row
                        for row in _parse_table(table)
                        if any(row.values())
                    ]

        vehicles_section = soup.find(id="vehicles")
        if vehicles_section is not None:
            table = vehicles_section.find("table")
            detail["vehicles"] = [row for row in _parse_table(table) if any(row.values())]

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
        start = int(cursor) if cursor else 0
        if start < 0:
            start = 0

        page_size = min(batch_size or self.page_size_cap, self.page_size_cap)
        remaining = limit

        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
            while True:
                payload = await self._fetch_search_page(client, start=start, length=page_size)
                offenders = payload.get("offenders") or []
                if remaining is not None:
                    offenders = offenders[:remaining]
                if not offenders:
                    return

                detail_htmls = await asyncio.gather(
                    *(self._fetch_detail_html(client, offender["id"]) for offender in offenders)
                )
                batch = [
                    {
                        "summary": offender,
                        "detail": self._parse_detail_html(detail_html),
                        "source_url": self.source_url,
                    }
                    for offender, detail_html in zip(offenders, detail_htmls, strict=False)
                ]

                next_start = start + len(offenders)
                total_items = _to_int(payload.get("totalItems")) or _to_int(payload.get("recordsTotal"))
                next_cursor = None
                if total_items is None or next_start < total_items:
                    next_cursor = str(next_start)
                yield batch, next_cursor

                if remaining is not None:
                    remaining -= len(offenders)
                    if remaining <= 0:
                        return

                if next_cursor is None:
                    return
                start = next_start

    def parse(self, raw_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return raw_payloads

    def normalize(self, parsed_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for record in parsed_records:
            summary = record.get("summary") or {}
            detail = record.get("detail") or {}
            external_id = summary.get("id")
            if not external_id:
                continue

            birthdate = _parse_mdy_date(detail.get("birthdate"))

            first_name = summary.get("firstName") or ""
            middle_name = summary.get("middleName") or ""
            last_name = summary.get("lastName") or ""
            full_name = ", ".join(
                [
                    part
                    for part in [
                        _compact_text(last_name),
                        " ".join(part for part in [_compact_text(first_name), _compact_text(middle_name)] if part),
                    ]
                    if part
                ]
            )
            if not full_name:
                full_name = _compact_text(detail.get("display_name")) or str(external_id)

            addresses = detail.get("addresses") or []
            if not addresses:
                fallback_address = {
                    "line1": summary.get("street") or None,
                    "city": summary.get("city") or None,
                    "state": "MI",
                    "postal_code": summary.get("postalCode") or None,
                    "county": summary.get("county") or None,
                }
                if any(value for key, value in fallback_address.items() if key != "state"):
                    addresses = [fallback_address]

            aliases = detail.get("aliases") or []
            offenses = detail.get("offenses") or []
            vehicles = detail.get("vehicles") or []
            scars_markings = detail.get("scars_markings") or []

            normalized.append(
                {
                    "external_id": str(external_id),
                    "full_name": full_name,
                    "risk_level": summary.get("compliant") or detail.get("compliance_status"),
                    "date_of_birth": birthdate.isoformat() if birthdate else None,
                    "race": detail.get("race"),
                    "sex": detail.get("sex") or summary.get("gender"),
                    "height_cm": None,
                    "weight_kg": None,
                    "eye_color": detail.get("eye_color"),
                    "hair_color": detail.get("hair_color"),
                    "demographics": {
                        "registration_number": detail.get("registration_number"),
                        "mdoc_number": detail.get("mdoc_number"),
                        "status": detail.get("status"),
                        "compliance_status": detail.get("compliance_status"),
                        "age": _to_int(detail.get("age") or summary.get("age")),
                        "last_verification_date": detail.get("last_verification_date"),
                        "county": summary.get("county"),
                        "postal_code": summary.get("postalCode"),
                        "image_url": detail.get("photo_url") or summary.get("imageUrl"),
                        "vehicles": vehicles,
                        "scars_markings": scars_markings,
                    },
                    "aliases": aliases,
                    "addresses": addresses,
                    "offenses": [
                        {
                            **offense,
                            "conviction_date": _parse_mdy_date(offense.get("conviction_date")),
                        }
                        for offense in offenses
                    ],
                    "photos": [{"image_url": detail.get("photo_url") or summary.get("imageUrl")}]
                    if detail.get("photo_url") or summary.get("imageUrl")
                    else [],
                    "source_url": self.source_url,
                    "raw_payload": {
                        "summary": {k: v for k, v in summary.items() if k != "imageUrl"},
                        "detail": detail,
                    },
                }
            )
        return normalized
