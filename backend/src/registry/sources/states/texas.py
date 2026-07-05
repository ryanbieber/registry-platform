from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

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


def _parse_address_text(value: Any, *, county: str | None = None) -> dict[str, Any] | None:
    text = _compact_text(value)
    if not text:
        return None

    match = re.match(
        r"^(?P<line1>.+?)\s*,\s*(?P<city>.+?)\s+(?P<state>[A-Z]{2})\s+(?P<postal>\d{5}(?:-\d{4})?)$",
        text,
    )
    if match:
        return {
            "line1": _compact_text(match.group("line1")),
            "line2": None,
            "city": _compact_text(match.group("city")),
            "state": _compact_text(match.group("state")),
            "postal_code": _compact_text(match.group("postal")),
            "county": county,
            "address_precision": "registry",
        }

    return {
        "line1": text,
        "line2": None,
        "city": None,
        "state": None,
        "postal_code": None,
        "county": county,
        "address_precision": "registry",
    }


def _extract_token_and_counties(html: str) -> tuple[str, list[dict[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    token_el = soup.find("input", {"name": "__RequestVerificationToken"})
    token = token_el.get("value") if token_el else None
    if not token:
        raise RuntimeError("Texas search page did not include a verification token")

    counties: list[dict[str, str]] = []
    select = soup.find("select", {"name": "COU_COD"})
    if select is None:
        raise RuntimeError("Texas county search page did not include a county selector")

    for option in select.find_all("option"):
        value = _compact_text(option.get("value"))
        label = _compact_text(option.get_text(" ", strip=True))
        if not value or not label or label == "Choose one...":
            continue
        counties.append({"code": value, "name": label})

    return token, counties


def _parse_search_results(html: str, *, county_code: str, county_name: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table", id="tblExportDownloads")
    if len(tables) < 2:
        return []

    results_table = tables[1]
    tbody = results_table.find("tbody") or results_table
    rows: list[dict[str, Any]] = []

    for tr in tbody.find_all("tr", recursive=False):
        cells = tr.find_all("td")
        if len(cells) < 5:
            continue
        name_cell = cells[0]
        link = name_cell.find("a", href=True)
        full_name = _compact_text(name_cell.get_text(" ", strip=True))
        if not full_name:
            continue

        detail_url = urljoin("https://sor.dps.texas.gov", link["href"]) if link else None
        sid = _compact_text(link.get("data-dpsnbr") if link else None)
        if not sid and detail_url and "Sid=" in detail_url:
            sid = detail_url.split("Sid=", 1)[1].split("&", 1)[0]

        rows.append(
            {
                "external_id": sid,
                "full_name": full_name,
                "birthdate_text": _compact_text(cells[1].get_text(" ", strip=True)),
                "sex": _compact_text(cells[2].get_text(" ", strip=True)),
                "race": _compact_text(cells[3].get_text(" ", strip=True)),
                "address_text": _compact_text(cells[4].get_text(" ", strip=True)),
                "county_code": county_code,
                "county_name": county_name,
                "detail_url": detail_url,
                "has_photo": (link.get("data-hasphoto") if link else None) == "True",
                "source_url": detail_url or "https://sor.dps.texas.gov/PublicSite/Search/Default/SearchByCounty",
                "raw_html": str(tr),
            }
        )

    return rows


def _find_text(root: ET.Element, path: str) -> str | None:
    elem = root.find(path)
    return _compact_text(elem.text if elem is not None else None)


def _parse_detail_xml(xml_text: str, *, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    root = ET.fromstring(xml_text)
    sid = _compact_text(_find_text(root, "DPS_NBR") or (summary or {}).get("external_id"))
    if not sid:
        raise RuntimeError("Texas rapsheet XML did not include a DPS number")

    names = root.findall("Names/Name")
    primary_name = None
    aliases: list[str] = []
    seen_aliases: set[str] = set()
    for name in names:
        name_text = _compact_text(name.findtext("NAM_TXT"))
        if not name_text:
            continue
        if _compact_text(name.findtext("TYP_COD")) == "B" and primary_name is None:
            primary_name = name_text
            continue
        if name_text in seen_aliases:
            continue
        seen_aliases.add(name_text)
        aliases.append(name_text)

    birthdates = root.findall("Birthdates/Birthdate")
    birthdate = None
    for birthdate_node in birthdates:
        birthdate = _parse_date(birthdate_node.findtext("DOB_DTE_formatted"))
        if birthdate:
            break

    search_address = _parse_address_text((summary or {}).get("address_text"), county=(summary or {}).get("county_name"))
    xml_addresses: list[dict[str, Any]] = []
    for address in root.findall("Addresses/Address"):
        line1 = _compact_text(address.findtext("AddressLine1"))
        line2 = _compact_text(address.findtext("AddressLine2"))
        reported_at = _parse_date(address.findtext("CRT_TMS_formatted"))
        status = _compact_text(address.findtext("PDV_COD_LIT"))
        if not any([line1, line2, reported_at, status]):
            continue
        xml_addresses.append(
            {
                "line1": line1,
                "line2": line2,
                "city": None,
                "state": "TX" if line1 or line2 else None,
                "postal_code": None,
                "county": (summary or {}).get("county_name"),
                "address_precision": "registry",
                "reported_at": reported_at,
                "status": status,
            }
        )

    addresses = [search_address] if search_address else []
    if not addresses and xml_addresses:
        first_address = xml_addresses[0]
        addresses.append(
            {
                "line1": first_address.get("line1"),
                "line2": first_address.get("line2"),
                "city": None,
                "state": first_address.get("state"),
                "postal_code": None,
                "county": first_address.get("county"),
                "address_precision": "registry",
            }
        )

    registration_events = []
    for event in root.findall("RegistrationEvents/RegistrationEvent"):
        registration_events.append(
            {
                "event_date": _parse_date(event.findtext("EVT_DTE_formatted")),
                "event_id": _compact_text(event.findtext("EventId")),
                "event_type": _compact_text(event.findtext("EVM_COD_LIT")),
                "ori": _compact_text(event.findtext("ORI_TXT")),
                "agency": _compact_text(event.findtext("ATR_TXT")),
            }
        )

    offenses = []
    for offense in root.findall("Offenses/Offense"):
        sentence_kind = _compact_text(offense.findtext("CPR_COD_LIT"))
        sentence_value = _compact_text(offense.findtext("CPR_VAL"))
        disposition_bits = [
            _compact_text(offense.findtext("OST_COD_LIT")),
            f"{sentence_kind}: {sentence_value}" if sentence_kind and sentence_value else sentence_kind,
        ]
        offenses.append(
            {
                "offense_name": _compact_text(offense.findtext("LEN_TXT")) or "Texas registry offense",
                "conviction_date": _parse_date(offense.findtext("CDD_DTE")),
                "disposition": "; ".join(part for part in disposition_bits if part),
                "statute": _compact_text(offense.findtext("CIT_TXT")),
                "victim_age": _compact_text(offense.findtext("AOV_NBR")),
                "victim_gender": _compact_text(offense.findtext("SOV_COD_LIT")),
            }
        )

    photos = []
    for photo in root.findall("Photos/Photo"):
        photo_id = _compact_text(photo.findtext("PhotoId"))
        is_current = _compact_text(photo.findtext("CUR_FLG")) == "Y"
        if is_current:
            image_url = f"https://sor.dps.texas.gov/PublicSite/Search/Rapsheet/CurrentPhoto?Sid={sid}"
        elif photo_id:
            image_url = f"https://sor.dps.texas.gov/PublicSite/Search/Rapsheet/Photo?photoId={photo_id}"
        else:
            continue
        photos.append(
            {
                "image_url": image_url,
                "captured_at": _parse_date(photo.findtext("POS_DTE_formatted")),
            }
        )

    notices = [
        _compact_text(notice.text)
        for notice in root.findall("Notices/Notice")
        if _compact_text(notice.text)
    ]

    detail = {
        "dps_number": sid,
        "registrant_id": _compact_text(root.findtext("IND_IDN")),
        "risk_level": _compact_text(root.findtext("RSK_COD_LIT")),
        "is_erd_future": _compact_text(root.findtext("IsErdFuture")),
        "expiration_term": _compact_text(root.findtext("ERT_COD_LIT")),
        "verification_period": _compact_text(root.findtext("VRP_COD_LIT")),
        "sex": _compact_text(root.findtext("SEX_COD_LIT")),
        "race": _compact_text(root.findtext("RAC_COD_LIT")),
        "ethnicity": _compact_text(root.findtext("ETH_COD_LIT")),
        "height_cm": _parse_height_cm(root.findtext("HGT_QTY_formatted")),
        "weight_kg": _parse_weight_kg(root.findtext("WGT_QTY")),
        "hair_color": _compact_text(root.findtext("HAI_COD_LIT")),
        "eye_color": _compact_text(root.findtext("EYE_COD_LIT")),
        "shoe_size": _compact_text(root.findtext("SSZ_COD_formatted")),
        "wardrobe_size": _compact_text(root.findtext("SWD_COD_formatted")),
        "aliases": aliases,
        "birthdate": birthdate,
        "birthdate_text": birthdate or _compact_text(summary.get("birthdate_text") if summary else None),
        "addresses": addresses,
        "registry_addresses": xml_addresses,
        "registration_events": registration_events,
        "offenses": offenses,
        "photos": photos,
        "notices": notices,
        "summary": summary or {},
    }

    return {
        "external_id": sid,
        "full_name": primary_name or _compact_text(summary.get("full_name") if summary else None) or sid,
        "date_of_birth": birthdate,
        "sex": detail["sex"] or _compact_text(summary.get("sex") if summary else None),
        "race": detail["race"] or _compact_text(summary.get("race") if summary else None),
        "ethnicity": detail["ethnicity"],
        "height_cm": detail["height_cm"],
        "weight_kg": detail["weight_kg"],
        "eye_color": detail["eye_color"],
        "hair_color": detail["hair_color"],
        "risk_level": detail["risk_level"],
        "demographics": detail,
        "aliases": aliases,
        "addresses": addresses,
        "offenses": offenses,
        "photos": photos,
        "source_url": (summary or {}).get("detail_url") or "https://sor.dps.texas.gov/PublicSite/Search/Default/SearchByCounty",
        "raw_payload": {
            "summary": summary or {},
            "detail": detail,
        },
    }


class TexasRegistryConnector(SourceConnector):
    name = "texas"
    state = "TX"
    source_url = "https://sor.dps.texas.gov/PublicSite/Search/Default/SearchByCounty"
    _search_url = "https://sor.dps.texas.gov/PublicSite/Search/Default/SearchByCounty"
    _search_page_url = "https://sor.dps.texas.gov/PublicSite/Search/Default/SearchByCounty"

    async def _fetch_search_page(self, client: httpx.AsyncClient) -> str:
        response = await client.get(self._search_page_url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        return response.text

    async def _fetch_county_results(self, client: httpx.AsyncClient, *, county_code: str, token: str) -> str:
        response = await client.post(
            self._search_url,
            data={
                "COU_COD": county_code,
                "__RequestVerificationToken": token,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": self._search_page_url,
                "User-Agent": "Mozilla/5.0",
            },
        )
        response.raise_for_status()
        return response.text

    async def _fetch_detail_xml(self, client: httpx.AsyncClient, sid: str) -> str:
        response = await client.get(
            f"https://sor.dps.texas.gov/PublicSite/Search/Rapsheet/GetRapsheetXml?sid={sid}",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        return response.text

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
        county_index = 0
        record_offset = 0
        if cursor:
            parts = cursor.split(":", 1)
            try:
                county_index = max(0, int(parts[0]))
                record_offset = max(0, int(parts[1])) if len(parts) > 1 else 0
            except ValueError:
                county_index = 0
                record_offset = 0

        headers = {"User-Agent": "Mozilla/5.0"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=20.0), verify=False, headers=headers) as client:
            search_page_html = await self._fetch_search_page(client)
            token, counties = _extract_token_and_counties(search_page_html)
            if county_index >= len(counties):
                return

            emitted = 0
            chunk_size = batch_size or 100
            for index in range(county_index, len(counties)):
                county = counties[index]
                results_html = await self._fetch_county_results(client, county_code=county["code"], token=token)
                rows = _parse_search_results(results_html, county_code=county["code"], county_name=county["name"])
                if not rows:
                    record_offset = 0
                    continue

                selected_rows = rows[record_offset:]
                record_offset = 0
                if limit is not None:
                    remaining = limit - emitted
                    if remaining <= 0:
                        return
                    selected_rows = selected_rows[:remaining]
                if not selected_rows:
                    continue

                for offset in range(0, len(selected_rows), chunk_size):
                    chunk = selected_rows[offset : offset + chunk_size]
                    detail_xmls = await asyncio.gather(
                        *(self._fetch_detail_xml(client, row["external_id"]) for row in chunk if row.get("external_id"))
                    )
                    detail_map = {
                        row["external_id"]: _parse_detail_xml(detail_xml, summary=row)
                        for row, detail_xml in zip(chunk, detail_xmls, strict=False)
                        if row.get("external_id")
                    }
                    batch = [detail_map[row["external_id"]] for row in chunk if row.get("external_id") in detail_map]
                    if not batch:
                        continue

                    emitted += len(batch)
                    next_offset = offset + len(chunk)
                    if next_offset < len(rows):
                        next_cursor = f"{index}:{next_offset}"
                    elif index + 1 < len(counties):
                        next_cursor = f"{index + 1}:0"
                    else:
                        next_cursor = None
                    yield batch, next_cursor
                    if limit is not None and emitted >= limit:
                        return

    def parse(self, raw_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return raw_payloads

    def normalize(self, parsed_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for record in parsed_records:
            external_id = _compact_text(record.get("external_id"))
            if not external_id:
                continue

            normalized.append(
                {
                    "external_id": f"tx:{external_id}",
                    "full_name": _compact_text(record.get("full_name")) or external_id,
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
