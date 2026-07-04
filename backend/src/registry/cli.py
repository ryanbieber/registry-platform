import csv
from pathlib import Path

import anyio
import typer
from sqlmodel import Session

from registry.db import engine
from registry.services import ingest_source, list_sources
from registry.sources import get_connector

app = typer.Typer(help="Registry platform CLI")


@app.command("ingest-source")
def ingest_source_command(source: str, dry_run: bool = True, limit: int | None = None) -> None:
    with Session(engine) as session:
        run = anyio.run(ingest_source, session, source, dry_run=dry_run, limit=limit)
        typer.echo(f"{run.source_name}:{run.status}:{run.id}")


@app.command("ingest-all")
def ingest_all(dry_run: bool = True, limit: int | None = None) -> None:
    for source in list_sources():
        ingest_source_command(source.name, dry_run=dry_run, limit=limit)


@app.command("validate-source")
def validate_source(source: str) -> None:
    connector = get_connector(source)
    typer.echo(f"{connector.name} ({connector.state}) -> {connector.source_url}")


@app.command("export-csv")
def export_csv(output: Path = Path("exports/registrants.csv")) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=["id", "external_id", "full_name", "risk_level", "last_seen"])
        writer.writeheader()
    typer.echo(f"Wrote skeleton CSV to {output}")


if __name__ == "__main__":
    app()
