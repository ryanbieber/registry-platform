from datetime import datetime
import csv
from pathlib import Path

from sqlmodel import Session, select

from registry.models import RegistrySource


def enriched_source_inventory_csv_path() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "reference" / "state_registry_access_enriched.csv"


def source_inventory_csv_path() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "reference" / "state_registry_access.csv"


def load_source_inventory_rows(csv_path: Path | None = None) -> list[dict[str, str]]:
    path = csv_path or (
        enriched_source_inventory_csv_path()
        if enriched_source_inventory_csv_path().exists()
        else source_inventory_csv_path()
    )
    with path.open(newline="", encoding="utf-8") as file_handle:
        return list(csv.DictReader(file_handle))


def parse_optional_int(value: str | None) -> int | None:
    if not value:
        return None
    return int(value)


def parse_optional_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def seed_registry_sources(session: Session, csv_path: Path | None = None) -> tuple[int, int]:
    inserted = 0
    updated = 0

    for row in load_source_inventory_rows(csv_path):
        statement = select(RegistrySource).where(
            RegistrySource.state == row["state"],
            RegistrySource.jurisdiction_type == row["jurisdiction_type"],
        )
        existing = session.exec(statement).first()
        payload = {
            "official_registry_url": row["official_registry_url"],
            "access_surface": row["access_surface"],
            "recommended_acquisition_path": row["recommended_acquisition_path"],
            "notes": row["notes"],
            "state_code": row.get("state_code") or None,
            "source_checked_on": row.get("directory_checked_on") or "2026-07-04",
            "registry_http_status": parse_optional_int(row.get("registry_http_status")),
            "final_registry_url": row.get("final_registry_url") or None,
            "registry_host": row.get("registry_host") or None,
            "registry_page_title": row.get("registry_page_title") or None,
            "registry_content_type": row.get("registry_content_type") or None,
            "vendor_name": row.get("vendor_name") or None,
            "robots_txt_url": row.get("robots_txt_url") or None,
            "robots_txt_status": parse_optional_int(row.get("robots_txt_status")),
            "metadata_retrieved_at": parse_optional_datetime(row.get("metadata_retrieved_at")),
            "metadata_error": row.get("metadata_error") or None,
        }

        if existing is None:
            session.add(
                RegistrySource(
                    state=row["state"],
                    jurisdiction_type=row["jurisdiction_type"],
                    **payload,
                )
            )
            inserted += 1
        else:
            for field, value in payload.items():
                setattr(existing, field, value)
            session.add(existing)
            updated += 1

    session.commit()
    return inserted, updated
