from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

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
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
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
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
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


def _parse_definition_list(container: BeautifulSoup) -> dict[str, str | None]:
    values: dict[str, str | None] = {}
    for dt in container.find_all("dt"):
        label = _compact_text(dt.get_text(" ", strip=True).rstrip(":"))
        dd = dt.find_next_sibling("dd")
        if not label:
            continue
        values[label] = _compact_text(dd.get_text(" ", strip=True)) if dd else None
    return values


def _parse_aliases(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    aliases = [alias.strip() for alias in re.split(r"[\n,]+", raw_value) if alias.strip()]
    seen: set[str] = set()
    result: list[str] = []
    for alias in aliases:
        if alias in seen:
            continue
        seen.add(alias)
        result.append(alias)
    return result


def _parse_address_block(address: Any, *, address_precision: str) -> dict[str, Any] | None:
    text = address.get_text("\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip() and line.strip() != "Show Map"]
    if not lines:
        return None

    line1 = lines[0]
    city = state = postal_code = county = None
    line2 = None

    city_line_index = None
    city_line_match = None
    for index in range(1, len(lines)):
        match = re.match(r"^(?P<city>.+?),\s*(?P<state>[A-Z]{2})\s*,?\s*(?P<postal>\d{5}(?:-\d{4})?)$", lines[index])
        if match:
            city_line_index = index
            city_line_match = match
            break

    if city_line_match is not None:
        city = _compact_text(city_line_match.group("city"))
        state = _compact_text(city_line_match.group("state"))
        postal_code = _compact_text(city_line_match.group("postal"))
        trailing = [line for line in lines[city_line_index + 1 :] if line]
        if trailing:
            county = trailing[0]
            if len(trailing) > 1:
                line2 = trailing[1]
    elif len(lines) > 1:
        line2 = lines[1]

    return {
        "line1": line1,
        "line2": line2,
        "city": city,
        "state": state or "ND",
        "postal_code": postal_code,
        "county": county,
        "address_precision": address_precision,
    }


def _parse_address_section(soup: BeautifulSoup, header_text: str, *, address_precision: str) -> list[dict[str, Any]]:
    card = None
    for candidate in soup.find_all("div", class_="card"):
        header = candidate.find("div", class_="card-header")
        if header is None:
            continue
        if _compact_text(header.get_text(" ", strip=True)) == header_text:
            card = candidate
            break
    if card is None:
        return []

    addresses: list[dict[str, Any]] = []
    for address in card.find_all("address"):
        parsed = _parse_address_block(address, address_precision=address_precision)
        if parsed:
            addresses.append(parsed)
    return addresses


def _parse_search_results(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, Any]] = []
    table = soup.find("table", id="tblOffender")
    if table is None:
        return rows

    for tr in table.select("tbody tr"):
        cells = tr.find_all("td")
        if len(cells) < 5:
            continue
        name_cell = cells[1]
        name = _compact_text(name_cell.get_text(" ", strip=True))
        if not name:
            continue

        detail_link = name_cell.find("a", href=re.compile(r"^/offender/details/"))
        photo_img = cells[0].find("img")
        residence_address = cells[3].find("address")
        map_link = cells[3].find("a", href=re.compile(r"^/offender/map-single/"))

        rows.append(
            {
                "full_name": name,
                "birthdate_text": _compact_text(cells[2].get_text(" ", strip=True)),
                "risk_level": _compact_text(cells[4].get_text(" ", strip=True)),
                "photo_url": photo_img.get("data-original") or photo_img.get("src") if photo_img else None,
                "detail_url": urljoin("https://sexoffender.nd.gov", detail_link["href"]) if detail_link else None,
                "residence_text": _compact_text(residence_address.get_text("\n", strip=True)) if residence_address else None,
                "map_url": urljoin("https://sexoffender.nd.gov", map_link["href"]) if map_link else None,
                "source_url": urljoin("https://sexoffender.nd.gov", detail_link["href"]) if detail_link else None,
                "raw_html": str(tr),
            }
        )
    return rows


def _parse_vehicle_rows(container: BeautifulSoup) -> list[dict[str, Any]]:
    table = container.find("table")
    if table is None:
        return []
    rows: list[dict[str, Any]] = []
    for tr in table.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in tr.find_all("td")]
        if not cells or "No information available" in cells[0]:
            continue
        if len(cells) < 4:
            continue
        rows.append(
            {
                "make": _compact_text(cells[0]),
                "color": _compact_text(cells[1]),
                "year": _to_int(cells[2]),
                "plate_number": _compact_text(cells[3]),
            }
        )
    return rows


def _parse_offenses(soup: BeautifulSoup) -> list[dict[str, Any]]:
    card = next(
        (
            candidate
            for candidate in soup.find_all("div", class_="card")
            if candidate.find("div", class_="card-header")
            and _compact_text(candidate.find("div", class_="card-header").get_text(" ", strip=True))
            == "Qualifying Offense Information"
        ),
        None,
    )
    if card is None:
        return []

    offenses: list[dict[str, Any]] = []
    for item in card.select(".list-group-item"):
        values = _parse_definition_list(item)
        offense_text = _compact_text(values.get("Offense"))
        statute = None
        offense_name = offense_text
        if offense_text and ";" in offense_text:
            offense_name, statute = [part.strip() or None for part in offense_text.split(";", 1)]
        offenses.append(
            {
                "offense_name": offense_name or "North Dakota registry offense",
                "conviction_date": _parse_date(values.get("Conviction Date")),
                "jurisdiction": _compact_text(values.get("Jurisdiction & State")),
                "disposition": _compact_text(values.get("Disposition")),
                "statute": statute,
            }
        )
    return offenses


def _parse_detail_html(html: str, *, detail_url: str | None = None, search_result: dict[str, Any] | None = None) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    primary_card = next(
        (
            candidate
            for candidate in soup.find_all("div", class_="card")
            if candidate.find("div", class_="card-header")
            and _compact_text(candidate.find("div", class_="card-header").get_text(" ", strip=True))
            == "Primary Information"
        ),
        None,
    )
    primary_info = _parse_definition_list(primary_card) if primary_card is not None else {}
    aliases: list[str] = []
    if primary_card is not None:
        for dt in primary_card.find_all("dt"):
            label = _compact_text(dt.get_text(" ", strip=True).rstrip(":"))
            if label != "Aliases":
                continue
            dd = dt.find_next_sibling("dd")
            aliases = _parse_aliases(dd.get_text("\n", strip=True) if dd else None)
            break
    photo = soup.find("img", id="primaryImgId")
    photo_url = photo.get("src") if photo else None

    addresses = []
    addresses.extend(_parse_address_section(soup, "Residence Addresses", address_precision="residence"))
    addresses.extend(_parse_address_section(soup, "Employer Addresses", address_precision="employment"))
    addresses.extend(_parse_address_section(soup, "School Addresses", address_precision="school"))

    vehicles_card = next(
        (
            candidate
            for candidate in soup.find_all("div", class_="card")
            if candidate.find("div", class_="card-header")
            and _compact_text(candidate.find("div", class_="card-header").get_text(" ", strip=True)) == "Vehicles"
        ),
        None,
    )
    vehicles = _parse_vehicle_rows(vehicles_card) if vehicles_card is not None else []

    primary_address = addresses[0] if addresses else None
    result = {
        "offender_id": detail_url.rstrip("/").split("/")[-1] if detail_url else None,
        "full_name": _compact_text(primary_info.get("Name")) or _compact_text(search_result.get("full_name"))
        if search_result
        else None,
        "aliases": aliases,
        "date_of_birth": _parse_date(primary_info.get("Birthdate")),
        "sex": _compact_text(primary_info.get("Sex")),
        "race": _compact_text(primary_info.get("Race")),
        "height_cm": _parse_height_cm(primary_info.get("Height")),
        "weight_kg": _parse_weight_kg(primary_info.get("Weight")),
        "eye_color": _compact_text(primary_info.get("Eye Color")),
        "hair_color": _compact_text(primary_info.get("Hair Color")),
        "risk_level": _compact_text(primary_info.get("Risk Level")),
        "registration_status": _compact_text(primary_info.get("Registration Status")),
        "ethnicity": _compact_text(primary_info.get("Ethnicity")),
        "demographics": {
            "birth_year": _to_int(primary_info.get("Birthdate")),
            "skin": _compact_text(primary_info.get("Skin")),
            "registration_expiration": _parse_date(primary_info.get("Registration Expiration")),
            "photo_url": photo_url,
            "vehicle_count": len(vehicles),
            "vehicles": vehicles,
        },
        "addresses": addresses,
        "offenses": _parse_offenses(soup),
        "photos": (
            [{"image_url": photo_url, "captured_at": None}] if photo_url else []
        ),
        "source_url": detail_url or (search_result.get("source_url") if search_result else None),
        "raw_payload": {
            "detail_url": detail_url,
            "search_result": search_result,
        },
    }

    if primary_address:
        result["demographics"]["primary_county"] = primary_address.get("county")
        result["demographics"]["primary_city"] = primary_address.get("city")

    return result


class NorthDakotaRegistryConnector(SourceConnector):
    name = "north-dakota"
    state = "ND"
    source_url = "https://sexoffender.nd.gov/offender/search"
    _search_url = "https://sexoffender.nd.gov/offender/name-search"
    _base_url = "https://sexoffender.nd.gov"
    _cached_records: list[dict[str, Any]] | None = None

    async def _fetch_search_page(self, client: httpx.AsyncClient) -> str:
        response = await client.get(self.source_url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        return response.text

    async def _fetch_search_results(self, client: httpx.AsyncClient, *, first: str = "", last: str = "") -> list[dict[str, Any]]:
        html = await self._fetch_search_page(client)
        soup = BeautifulSoup(html, "html.parser")
        token_el = soup.find("input", {"name": "__RequestVerificationToken"})
        token = token_el.get("value") if token_el else None
        if not token:
            raise RuntimeError("North Dakota search page did not include a verification token")

        response = await client.post(
            self._search_url,
            data={
                "Search.FirstName": first,
                "Search.LastName": last,
                "__RequestVerificationToken": token,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": self.source_url,
                "User-Agent": "Mozilla/5.0",
            },
        )
        response.raise_for_status()
        return _parse_search_results(response.text)

    async def _fetch_detail_html(self, client: httpx.AsyncClient, detail_url: str) -> str:
        response = await client.get(detail_url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        return response.text

    async def _records(self) -> list[dict[str, Any]]:
        if self._cached_records is not None:
            return self._cached_records

        headers = {"User-Agent": "Mozilla/5.0"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=20.0), headers=headers) as client:
            search_results = await self._fetch_search_results(client, first="", last="")
            detail_rows = [row for row in search_results if row.get("detail_url")]
            detail_payloads = await asyncio.gather(
                *(self._fetch_detail_html(client, row["detail_url"]) for row in detail_rows)
            )
        merged = [
            _parse_detail_html(detail_html, detail_url=row.get("detail_url"), search_result=row)
            for row, detail_html in zip(detail_rows, detail_payloads, strict=False)
        ]
        self._cached_records = merged
        return merged

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
        seen = 0
        headers = {"User-Agent": "Mozilla/5.0"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=20.0), headers=headers) as client:
            search_results = await self._fetch_search_results(client, first="", last="")
            if limit is not None:
                search_results = search_results[:limit]
            for offset in range(0, len(search_results), batch_limit):
                batch_rows = search_results[offset : offset + batch_limit]
                detail_rows = [row for row in batch_rows if row.get("detail_url")]
                detail_payloads = await asyncio.gather(
                    *(self._fetch_detail_html(client, row["detail_url"]) for row in detail_rows)
                )
                merged = [
                    _parse_detail_html(detail_html, detail_url=row.get("detail_url"), search_result=row)
                    for row, detail_html in zip(detail_rows, detail_payloads, strict=False)
                ]
                if not merged:
                    continue
                seen += len(merged)
                yield merged, None
                if limit is not None and seen >= limit:
                    return

    def parse(self, raw_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return raw_payloads

    def normalize(self, parsed_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for record in parsed_records:
            offender_id = _compact_text(record.get("offender_id"))
            if not offender_id:
                continue

            normalized.append(
                {
                    "external_id": f"nd:{offender_id}",
                    "full_name": _compact_text(record.get("full_name")) or offender_id,
                    "date_of_birth": _parse_date(record.get("date_of_birth")),
                    "sex": _compact_text(record.get("sex")),
                    "race": _compact_text(record.get("race")),
                    "ethnicity": _compact_text(record.get("ethnicity")),
                    "height_cm": record.get("height_cm"),
                    "weight_kg": record.get("weight_kg"),
                    "eye_color": _compact_text(record.get("eye_color")),
                    "hair_color": _compact_text(record.get("hair_color")),
                    "risk_level": _compact_text(record.get("risk_level")),
                    "demographics": record.get("demographics") or None,
                    "aliases": record.get("aliases") or [],
                    "addresses": record.get("addresses") or [],
                    "offenses": record.get("offenses") or [],
                    "photos": record.get("photos") or [],
                    "source_url": record.get("source_url") or self.source_url,
                    "raw_payload": record,
                }
            )
        return normalized
