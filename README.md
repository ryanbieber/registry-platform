# Registry Platform

Skeleton project for a unified U.S. sex offender registry data platform with a FastAPI backend, React frontend, Postgres/PostGIS persistence, and source-specific ingestion connectors.

## Stack

- Backend: Python 3.12, `uv`, FastAPI, SQLModel, Alembic, Pydantic, Typer, `httpx`, `pytest`
- Frontend: React, TypeScript, Vite
- Data: Postgres + PostGIS
- Local orchestration: Docker Compose

## Repository layout

```text
registry-platform/
  .gitignore
  backend/
    pyproject.toml
    uv.lock
    src/registry/
    migrations/
    tests/
  frontend/
    package.json
    src/
  docs/
  data/
  docker-compose.yml
  README.md
```

## Backend skeleton highlights

- FastAPI entrypoint: `backend/src/registry/api/main.py`
- CLI entrypoint: `backend/src/registry/cli.py`
- Source connector interface in `backend/src/registry/sources/base.py`
- Example state connector stub in `backend/src/registry/sources/states/california.py`
- Initial Alembic schema includes:
  - `registrants`
  - `aliases`
  - `addresses`
  - `offenses`
  - `photos`
  - `source_records`
  - `ingestion_runs`

The connector skeleton enforces a staged ingestion pipeline:

1. `fetch()`
2. `parse()`
3. `normalize()`
4. `upsert()`

Raw source payloads, source URL, source state, `last_seen`, and ingestion run IDs are explicitly modeled for auditability.

## Frontend skeleton highlights

- Search registrants page
- Registrant detail page
- Source status page
- Search filters component
- Results table component
- Address/map placeholder component
- Source ingestion status panel component

## Research artifacts

- State registry access inventory overview: `docs/state-registry-access.md`
- State registry access CSV: `data/reference/state_registry_access.csv`

These files are intended to help plan compliant connectors around official registry entry points, not to justify scraping.

## Local development

### Backend

```bash
cd backend
uv sync
uv run uvicorn registry.api.main:app --reload
uv run pytest
uv run registry validate-source california
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Docker Compose

```bash
docker compose up
```

## API surface

- `GET /health`
- `GET /registrants`
- `GET /registrants/{id}`
- `GET /sources`
- `POST /ingest/{source}`

## CLI surface

- `registry ingest-source <source>`
- `registry ingest-all`
- `registry validate-source <source>`
- `registry export-csv`

## Legal and ethical notes

- This repository is a structural starting point only. It does not implement live scraping or bulk extraction.
- The state inventory in `data/reference/state_registry_access.csv` is a planning aid. Each jurisdiction still needs a fresh terms and access review before any connector is built.
- Any future source integration should respect `robots.txt`, published rate limits, and each registry's terms of use.
- Ingestion should be conservative, source-specific, and reviewable. Avoid aggressive crawling, circumvention, or evasion techniques.
- Source registries may contain incomplete or inconsistent fields. Treat race, address precision, risk level, and demographic attributes as nullable and non-authoritative.
- Address data may require reduced precision or display safeguards depending on source policy and legal constraints.
- Raw payload retention improves auditability, but downstream storage, access controls, and retention policies must be reviewed with legal counsel before production use.
