from sqlmodel import Session, SQLModel, create_engine, select

from registry.models import RegistrySource
from registry.services import list_sources
from registry.source_inventory import load_source_inventory_rows, seed_registry_sources


def test_inventory_csv_has_expected_rows() -> None:
    rows = load_source_inventory_rows()
    assert len(rows) == 51
    assert any(row["state"] == "California" for row in rows)
    assert any(row["state"] == "Texas" and row["state_code"] == "TX" for row in rows)


def test_seed_registry_sources() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine, tables=[RegistrySource.__table__])

    with Session(engine) as session:
        inserted, updated = seed_registry_sources(session)
        assert inserted == 51
        assert updated == 0

        rows = session.exec(select(RegistrySource)).all()
        assert len(rows) == 51

        seeded_sources = list_sources(session)
        california = next(row for row in seeded_sources if row.state == "California")
        assert california.official_registry_url == "https://www.meganslaw.ca.gov/"
        assert california.supports_fetch is True
        assert california.state_code == "CA"
        assert california.registry_http_status == 200
        assert california.registry_page_title == "Disclaimer - Megan's Law Website"
