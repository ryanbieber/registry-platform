import csv
from pathlib import Path

from sqlmodel import Session, select

from registry.models import RegistrySource


def source_inventory_csv_path() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "reference" / "state_registry_access.csv"


def load_source_inventory_rows(csv_path: Path | None = None) -> list[dict[str, str]]:
    path = csv_path or source_inventory_csv_path()
    with path.open(newline="", encoding="utf-8") as file_handle:
        return list(csv.DictReader(file_handle))


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
