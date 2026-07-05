from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin, urlparse

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
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date().isoformat()
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


def _parse_county_options(html: str) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    seen: set[str] = set()
    for text, value in re.findall(r'\{"Text":"([^"]+)","Value":"([^"]+)"\}', html):
        if value in seen:
            continue
        seen.add(value)
        options.append({"name": text, "id": value})
    return options


def _parse_search_results(html: str) -> tuple[list[dict[str, str]], int]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "/Registry/Offender/" not in href:
            continue
        offender_code = urlparse(href).path.rstrip("/").split("/")[-1]
        if offender_code in seen:
            continue
        seen.add(offender_code)
        links.append(
            {
                "offender_code": offender_code,
                "detail_url": urljoin("https://sor.nebraska.gov", href),
            }
        )

    page_numbers = [
        int(anchor.get_text(" ", strip=True))
        for anchor in soup.find_all("a", href=True)
        if "Page=" in anchor["href"] and anchor.get_text(" ", strip=True).isdigit()
    ]
    total_pages = max(page_numbers) if page_numbers else 1
    return links, total_pages


def _extract_text_after_label(container: BeautifulSoup, label: str) -> str | None:
    pattern = re.compile(rf"^{re.escape(label)}\s*:?\s*", re.IGNORECASE)
    for node in container.select("div.info_line"):
        text = node.get_text(" ", strip=True)
        if pattern.match(text):
            return pattern.sub("", text).strip() or None
    return None


def _parse_addresses(soup: BeautifulSoup) -> list[dict[str, Any]]:
    addresses_root = soup.find(id="addresses")
    if addresses_root is None:
        return []

    addresses: list[dict[str, Any]] = []
    for address_block in addresses_root.select("div.address"):
        lines = [line.strip() for line in address_block.get_text("\n", strip=True).splitlines() if line.strip()]
        if not lines:
            continue

        reported_on = None
        for line in lines:
            if line.lower().startswith("address reported on"):
                reported_on = line.split(":", 1)[-1].strip() or None
                break

        content_lines = [line for line in lines if not line.lower().startswith("address reported on")]
        address_type = content_lines[0] if content_lines else None
        if address_type is None:
            continue

        county = None
        city = None
        state = None
        postal_code = None

        city_index = None
        for index in range(1, len(content_lines)):
            if re.search(r",\s*[A-Z]{2,3}\s+\S+", content_lines[index]):
                city_index = index
                break
        if city_index is None:
            continue

        street_lines = content_lines[1:city_index]
        city_line = content_lines[city_index]
        city_match = re.match(r"^(.*?),\s*([A-Z]{2,3})\s+([A-Z0-9\- ]+)$", city_line)
        if city_match:
            city = _compact_text(city_match.group(1))
            state = _compact_text(city_match.group(2))
            postal_code = _compact_text(city_match.group(3))

        trailing_lines = content_lines[city_index + 1 :]
        for index, line in enumerate(trailing_lines):
            if line == "County" and index > 0:
                county = trailing_lines[index - 1]
                break
            if line.endswith("County"):
                county = line.replace("County", "").strip() or None
                break

        line1 = street_lines[0] if street_lines else None
        line2 = street_lines[1] if len(street_lines) > 1 else None

        if any([line1, line2, city, state, postal_code, county]):
            addresses.append(
                {
                    "line1": line1,
                    "line2": line2,
                    "city": city,
                    "state": state or "NE",
                    "postal_code": postal_code,
                    "county": county,
                    "reported_on": reported_on,
                    "address_type": address_type,
                }
            )
    return addresses


def _parse_schools(soup: BeautifulSoup) -> list[str]:
    schools_root = soup.find(id="schools")
    if schools_root is None:
        return []
    text = schools_root.get_text("\n", strip=True)
    if "No schools listed" in text:
        return []
    return [line.strip() for line in text.splitlines() if line.strip() and "Offender attending:" not in line]


def _parse_vehicles(soup: BeautifulSoup) -> list[dict[str, Any]]:
    vehicles_root = soup.find(id="vehicles")
    if vehicles_root is None:
        return []

    vehicles: list[dict[str, Any]] = []
    for dl in vehicles_root.find_all("dl"):
        for text in [line.strip() for line in dl.get_text("\n", strip=True).splitlines() if line.strip()]:
            vehicles.append({"description": text})
    return vehicles


def _parse_offenses(soup: BeautifulSoup) -> list[dict[str, Any]]:
    heading = soup.find("h2", string=lambda text: text and "Sex Crime Conviction(s)" in text)
    if heading is None:
        return []

    offenses: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    fields: list[tuple[str, str]] = [
        ("Crime", "offense_name"),
        ("Statute Number(s)", "statute"),
        ("Jurisdiction", "jurisdiction"),
        ("Court", "court"),
        ("Conviction Date", "conviction_date"),
        ("Place of Crime", "place_of_crime"),
        ("Victim of Crime", "victim_age"),
    ]
    field_map = dict(fields)

    sibling = heading.find_next_sibling()
    while sibling is not None:
        if sibling.name == "div" and "info_line" in (sibling.get("class") or []):
            label_text = sibling.get_text(" ", strip=True)
            for label, field_name in fields:
                if label_text.startswith(f"{label}:"):
                    value = label_text.split(":", 1)[-1].strip() or None
                    if label == "Crime" and current:
                        offenses.append(current)
                        current = {}
                    current[field_name] = value
                    break
        elif sibling.name == "hr":
            if current:
                offenses.append(current)
                current = {}
        elif sibling.name == "div" and "info" in (sibling.get("class") or []) and "This public notification" in sibling.get_text(" ", strip=True):
            break
        sibling = sibling.find_next_sibling()

    if current:
        offenses.append(current)
    return offenses


class NebraskaRegistryConnector(SourceConnector):
    name = "nebraska"
    state = "NE"
    source_url = "https://sor.nebraska.gov/Registry/RegionSearch"
    _base_url = "https://sor.nebraska.gov"
    _search_url = "https://sor.nebraska.gov/Registry/Search"
    _cached_counties: list[dict[str, str]] | None = None
    _cached_records: list[dict[str, Any]] | None = None

    async def _fetch_counties(self, client: httpx.AsyncClient) -> list[dict[str, str]]:
        if self._cached_counties is not None:
            return self._cached_counties
        response = await client.get(self.source_url)
        response.raise_for_status()
        counties = _parse_county_options(response.text)
        self._cached_counties = counties
        return counties

    async def _fetch_search_page(self, client: httpx.AsyncClient, *, county_id: str, page: int) -> str:
        response = await client.get(
            self._search_url,
            params={"SearchType": "Region", "CountyId": county_id, "Page": page},
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        return response.text

    async def _fetch_detail_html(self, client: httpx.AsyncClient, detail_url: str) -> str:
        response = await client.get(detail_url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        return response.text

    async def _records(self) -> list[dict[str, Any]]:
        if self._cached_records is not None:
            return self._cached_records

        headers = {"User-Agent": "Mozilla/5.0"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0), verify=False, headers=headers) as client:
            counties = await self._fetch_counties(client)
            seen: set[str] = set()
            records: list[dict[str, Any]] = []

            for county in counties:
                county_id = county["id"]
                county_name = county["name"]
                first_page_html = await self._fetch_search_page(client, county_id=county_id, page=1)
                result_links, total_pages = _parse_search_results(first_page_html)
                if not result_links:
                    continue

                for page_number in range(1, total_pages + 1):
                    page_html = first_page_html if page_number == 1 else await self._fetch_search_page(
                        client,
                        county_id=county_id,
                        page=page_number,
                    )
                    page_links, _page_total = _parse_search_results(page_html)
                    for link in page_links:
                        offender_code = link["offender_code"]
                        if offender_code in seen:
                            continue
                        seen.add(offender_code)
                        detail_html = await self._fetch_detail_html(client, link["detail_url"])
                        records.append(
                            {
                                "county_id": county_id,
                                "county_name": county_name,
                                "offender_code": offender_code,
                                "detail_url": link["detail_url"],
                                "detail_html": detail_html,
                                "source_url": link["detail_url"],
                            }
                        )

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
        start_index = int(cursor) if cursor else 0
        if start_index < 0:
            start_index = 0

        batch_limit = batch_size or 12
        remaining = limit
        absolute_index = 0
        current_batch: list[dict[str, Any]] = []

        headers = {"User-Agent": "Mozilla/5.0"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0), verify=False, headers=headers) as client:
            counties = await self._fetch_counties(client)
            seen: set[str] = set()

            for county in counties:
                county_id = county["id"]
                county_name = county["name"]
                first_page_html = await self._fetch_search_page(client, county_id=county_id, page=1)
                result_links, total_pages = _parse_search_results(first_page_html)
                if not result_links:
                    continue

                for page_number in range(1, total_pages + 1):
                    page_html = first_page_html if page_number == 1 else await self._fetch_search_page(
                        client,
                        county_id=county_id,
                        page=page_number,
                    )
                    page_links, _page_total = _parse_search_results(page_html)
                    if not page_links:
                        continue

                    detail_links: list[dict[str, str]] = []
                    for link in page_links:
                        offender_code = link["offender_code"]
                        if offender_code in seen:
                            continue
                        seen.add(offender_code)
                        detail_links.append(link)

                    if not detail_links:
                        continue

                    detail_htmls = await asyncio.gather(
                        *(self._fetch_detail_html(client, link["detail_url"]) for link in detail_links)
                    )
                    page_records = [
                        {
                            "county_id": county_id,
                            "county_name": county_name,
                            "offender_code": link["offender_code"],
                            "detail_url": link["detail_url"],
                            "detail_html": detail_html,
                            "source_url": link["detail_url"],
                        }
                        for link, detail_html in zip(detail_links, detail_htmls, strict=False)
                    ]

                    for record in page_records:
                        if absolute_index < start_index:
                            absolute_index += 1
                            continue

                        current_batch.append(record)
                        absolute_index += 1
                        if remaining is not None:
                            remaining -= 1

                        if len(current_batch) >= batch_limit:
                            next_cursor = str(absolute_index)
                            if remaining is not None and remaining <= 0:
                                next_cursor = None
                            yield current_batch, next_cursor
                            current_batch = []

                        if remaining is not None and remaining <= 0:
                            if current_batch:
                                yield current_batch, None
                            return

        if current_batch:
            yield current_batch, None

    def parse(self, raw_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return raw_payloads

    def normalize(self, parsed_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for record in parsed_records:
            detail_html = record.get("detail_html")
            if not detail_html:
                continue
            soup = BeautifulSoup(detail_html, "html.parser")

            title = _compact_text(soup.title.get_text(" ", strip=True)) if soup.title else None
            full_name = None
            if title and ":" in title:
                full_name = title.split(":", 1)[-1].strip() or None
            if not full_name:
                h1 = soup.find("h1")
                full_name = _compact_text(h1.get_text(" ", strip=True)) if h1 else None

            dob = _parse_date(_extract_text_after_label(soup, "Date of Birth"))
            registration_duration = _extract_text_after_label(soup, "Registration Duration")
            race = _extract_text_after_label(soup, "Race")
            sex = _extract_text_after_label(soup, "Sex")
            height = _extract_text_after_label(soup, "Height")
            weight = _extract_text_after_label(soup, "Weight")
            hair = _extract_text_after_label(soup, "Hair")
            eyes = _extract_text_after_label(soup, "Eyes")
            alias_text = _extract_text_after_label(soup, "Alias(s)") or ""
            aliases = [alias.strip() for alias in re.split(r"[;|]\s*|\n+", alias_text) if alias.strip()]

            image_url = None
            for img in soup.find_all("img", src=True):
                src = img["src"]
                if src.startswith("/Image/"):
                    image_url = urljoin(self._base_url, src)
                    break

            addresses = []
            for address in _parse_addresses(soup):
                address.pop("reported_on", None)
                address.pop("address_type", None)
                if address:
                    addresses.append(address)

            schools = _parse_schools(soup)
            vehicles = _parse_vehicles(soup)
            offenses = _parse_offenses(soup)

            normalized.append(
                {
                    "external_id": f"ne:{record['offender_code']}",
                    "full_name": full_name or record["offender_code"],
                    "date_of_birth": dob,
                    "race": race,
                    "sex": sex,
                    "height_cm": None,
                    "weight_kg": None,
                    "eye_color": eyes,
                    "hair_color": hair,
                    "risk_level": registration_duration,
                    "demographics": {
                        "county": record.get("county_name"),
                        "county_id": record.get("county_id"),
                        "registration_duration": registration_duration,
                        "schools": schools,
                        "vehicles": vehicles,
                        "vehicle_count": len(vehicles),
                        "image_url": image_url,
                    },
                    "aliases": aliases,
                    "addresses": addresses,
                    "offenses": [
                        {
                            "offense_name": offense.get("offense_name") or "Nebraska registry offense",
                            "statute": offense.get("statute"),
                            "conviction_date": _parse_date(offense.get("conviction_date")),
                            "disposition": offense.get("court"),
                            "victim_age": offense.get("victim_age"),
                        }
                        for offense in offenses
                    ],
                    "photos": [{"image_url": image_url}] if image_url else [],
                    "source_url": record.get("source_url") or self.source_url,
                    "raw_payload": record,
                }
            )
        return normalized
