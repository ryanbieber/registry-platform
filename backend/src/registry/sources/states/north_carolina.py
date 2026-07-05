from __future__ import annotations

import io
import re
import zipfile
from collections.abc import AsyncIterator
from html import unescape
from typing import Any

import httpx

from registry.sources.base import SourceConnector


def _parse_hidden_field(html: str, name: str) -> str | None:
    pattern = rf'name="{re.escape(name)}"[^>]*value="([^"]*)"'
    match = re.search(pattern, html, re.IGNORECASE)
    if match is None:
        return None
    return unescape(match.group(1))


def _split_fixed_width_spans(separator_line: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for index, char in enumerate(separator_line):
        if char == "-":
            if start is None:
                start = index
        elif start is not None:
            spans.append((start, index))
            start = None
    if start is not None:
        spans.append((start, len(separator_line)))
    return spans


def _parse_fixed_width_table(text: str) -> list[dict[str, str]]:
    lines = [line.rstrip("\r") for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return []

    header_line = lines[0]
    separator_line = lines[1]
    spans = _split_fixed_width_spans(separator_line)
    columns = []
    for index, (start, end) in enumerate(spans, start=1):
        column_name = header_line[start:end].strip()
        columns.append(column_name or f"column_{index}")

    rows: list[dict[str, str]] = []
    for line in lines[2:]:
        values = []
        for start, end in spans:
            values.append(line[start:end].strip())
        if any(values):
            rows.append(dict(zip(columns, values, strict=False)))
    return rows


def _rows_by_key(rows: list[dict[str, str]], key: str) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        value = row.get(key)
        if not value:
            continue
        grouped.setdefault(value.strip(), []).append(row)
    return grouped


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def _optional_int(value: Any) -> int | None:
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


class NorthCarolinaRegistryConnector(SourceConnector):
    name = "north-carolina"
    state = "NC"
    source_url = "https://sexoffender.ncsbi.gov/stats.aspx"
    _download_target = "datadownloadbutton"
    _cached_records: list[dict[str, Any]] | None = None

    async def _download_archive(self) -> bytes:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0), headers=headers) as client:
            response = await client.get(self.source_url)
            response.raise_for_status()
            payload = {
                "__EVENTTARGET": self._download_target,
                "__EVENTARGUMENT": "",
            }
            for field_name in ["__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION", "__VIEWSTATEENCRYPTED"]:
                value = _parse_hidden_field(response.text, field_name)
                if value is not None:
                    payload[field_name] = value

            download = await client.post(self.source_url, data=payload)
            download.raise_for_status()
            if download.headers.get("content-type", "").lower().startswith("application/zip"):
                return download.content
            raise ValueError("North Carolina registry download did not return a zip archive")

    def _extract_table(self, archive: zipfile.ZipFile, filename: str) -> list[dict[str, str]]:
        try:
            data = archive.read(filename)
        except KeyError:
            return []
        return _parse_fixed_width_table(data.decode("utf-8", errors="replace"))

    async def _records(self) -> list[dict[str, Any]]:
        if self._cached_records is not None:
            return self._cached_records

        archive_bytes = await self._download_archive()
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            individuals = self._extract_table(archive, "Public Individual Information.txt")
            names = _rows_by_key(self._extract_table(archive, "Public Name Information.txt"), "SexRegistrationNumber")
            addresses = _rows_by_key(self._extract_table(archive, "Public Address Information.txt"), "SexRegistrationNumber")
            offenses = _rows_by_key(self._extract_table(archive, "Public Offense Information.txt"), "SexRegistrationNumber")
            violations = _rows_by_key(self._extract_table(archive, "Public Violation Information.txt"), "SexRegistrationNumber")
            birth_dates = _rows_by_key(self._extract_table(archive, "Public BirthDate Information.txt"), "SexRegistrationNumber")
            conviction_names = _rows_by_key(
                self._extract_table(archive, "Public Conviction Name Information.txt"),
                "SexRegistrationNumber",
            )
            scar_marks = _rows_by_key(
                self._extract_table(archive, "Public ScarMarkTattoo Information.txt"),
                "SexRegistrationNumber",
            )
            non_resident = _rows_by_key(
                self._extract_table(archive, "Public NonResident Information.txt"),
                "SexRegistrationNumber",
            )

        records: list[dict[str, Any]] = []
        for individual in individuals:
            sex_registration_number = (individual.get("SexRegistrationNumber") or "").strip()
            if not sex_registration_number:
                continue

            records.append(
                {
                    "sex_registration_number": sex_registration_number,
                    "individual": individual,
                    "aliases": [row.get("FullName", "") for row in names.get(sex_registration_number, [])],
                    "addresses": addresses.get(sex_registration_number, []),
                    "offenses": offenses.get(sex_registration_number, []),
                    "violations": violations.get(sex_registration_number, []),
                    "birth_dates": birth_dates.get(sex_registration_number, []),
                    "conviction_names": conviction_names.get(sex_registration_number, []),
                    "scar_marks": scar_marks.get(sex_registration_number, []),
                    "non_resident": non_resident.get(sex_registration_number, []),
                    "source_url": self.source_url,
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
        records = await self._records()
        start_index = int(cursor) if cursor else 0
        if start_index < 0:
            start_index = 0
        selected = records[start_index:]
        if limit is not None:
            selected = selected[:limit]

        batch_limit = batch_size or 500
        for offset in range(0, len(selected), batch_limit):
            batch = selected[offset : offset + batch_limit]
            next_index = start_index + offset + len(batch)
            next_cursor = str(next_index) if next_index < start_index + len(selected) else None
            yield batch, next_cursor

    def parse(self, raw_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return raw_payloads

    def normalize(self, parsed_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for record in parsed_records:
            individual = record["individual"]
            sex_registration_number = (individual.get("SexRegistrationNumber") or "").strip()
            full_name = (individual.get("FullName") or sex_registration_number).strip() or sex_registration_number

            current_address = {
                "line1": individual.get("AddressLine1") or None,
                "line2": individual.get("AddressLine2") or None,
                "city": individual.get("City") or None,
                "state": individual.get("State") or None,
                "postal_code": individual.get("Zip") or None,
                "county": individual.get("CountyName") or None,
            }
            address_rows = [current_address] if any(current_address.values()) else []
            for address_row in record.get("addresses") or []:
                address_candidate = {
                    "line1": address_row.get("AddressLine1") or None,
                    "line2": address_row.get("AddressLine2") or None,
                    "city": address_row.get("City") or None,
                    "state": address_row.get("State") or None,
                    "postal_code": address_row.get("Zip") or None,
                    "county": address_row.get("CountyName") or None,
                }
                if any(address_candidate.values()) and address_candidate not in address_rows:
                    address_rows.append(address_candidate)

            aliases = _unique_strings([alias for alias in record.get("aliases", []) if alias])
            for conviction_row in record.get("conviction_names") or []:
                aliases.extend(
                    name
                    for name in _unique_strings([conviction_row.get("FullName") or ""])
                    if name != full_name
                )
            flat_aliases = _unique_strings([alias for alias in aliases if isinstance(alias, str)])

            offense_rows = []
            for offense_row in record.get("offenses") or []:
                offense_name = offense_row.get("NCGeneralStatuteDescription") or offense_row.get("OffenseQualifierDescription")
                offense_rows.append(
                    {
                        "offense_name": offense_name or offense_row.get("NCGeneralStatute") or "North Carolina registry offense",
                        "statute": offense_row.get("NCGeneralStatute") or None,
                        "offense_date": offense_row.get("OffenseDate") or None,
                        "conviction_date": offense_row.get("ConvictionDate") or None,
                    }
                )

            demographics = {
                "department_of_correction_number": individual.get("DepartmentofCorrectionNumber") or None,
                "registration_type": individual.get("RegistrationType") or None,
                "public_registration_type_description": individual.get("PublicRegistrationTypeDescription") or None,
                "pending_source_code": individual.get("PendingSourceCode") or None,
                "pending_source_code_description": individual.get("PendingSourceCodeDescription") or None,
                "registration_date": individual.get("RegistrationDate") or None,
                "primary_birth_date": individual.get("PrimaryBirthDate") or None,
                "alternate_birth_dates": [row.get("BirthDate") or None for row in record.get("birth_dates") or [] if row.get("BirthDate")],
                "violations": [row.get("ViolationDescription") or row.get("ViolationType") for row in record.get("violations") or [] if row.get("ViolationDescription") or row.get("ViolationType")],
                "scar_marks": [
                    {
                        "code": row.get("NCICScarMarkTattoo") or None,
                        "text": row.get("ScarMarkTattooText") or None,
                        "description": row.get("ScarMarkTattooDescription") or None,
                    }
                    for row in record.get("scar_marks") or []
                    if any(row.values())
                ],
                "non_resident": [
                    {
                        "in_state_address_line1": row.get("NonResidentInStateAddressLine1") or None,
                        "in_state_address_line2": row.get("NonResidentInStateAddressLine2") or None,
                        "in_state_city": row.get("NonResidentInStateCity") or None,
                        "in_state_state": row.get("NonResidentInStateState") or None,
                        "in_state_zip": row.get("NonResidentInStateZip") or None,
                        "out_of_state_address_line1": row.get("NonResidentOutofStateAddressLine1") or None,
                        "out_of_state_address_line2": row.get("NonResidentOutofStateAddressLine2") or None,
                        "out_of_state_city": row.get("NonResidentOutofStateCity") or None,
                        "out_of_state_state": row.get("NonResidentOutofStateState") or None,
                        "out_of_state_zip": row.get("NonResidentOutofStateZip") or None,
                        "school_business_name": row.get("SchoolBusinessName") or None,
                    }
                    for row in record.get("non_resident") or []
                    if any(row.values())
                ],
            }

            normalized.append(
                {
                    "external_id": sex_registration_number,
                    "full_name": full_name,
                    "date_of_birth": individual.get("PrimaryBirthDate") or None,
                    "race": individual.get("Race") or None,
                    "sex": individual.get("Sex") or None,
                    "height_cm": _optional_int(individual.get("Height")),
                    "weight_kg": _optional_int(individual.get("Weight")),
                    "eye_color": individual.get("EyeColor") or None,
                    "hair_color": individual.get("HairColor") or None,
                    "demographics": demographics,
                    "aliases": flat_aliases,
                    "addresses": address_rows,
                    "offenses": offense_rows,
                    "source_url": self.source_url,
                    "raw_payload": {
                        "sex_registration_number": sex_registration_number,
                        "individual": individual,
                        "supplemental_counts": {
                            "aliases": len(flat_aliases),
                            "addresses": len(address_rows),
                            "offenses": len(offense_rows),
                            "violations": len(record.get("violations") or []),
                            "birth_dates": len(record.get("birth_dates") or []),
                            "scar_marks": len(record.get("scar_marks") or []),
                            "non_resident": len(record.get("non_resident") or []),
                        },
                    },
                }
            )
        return normalized
