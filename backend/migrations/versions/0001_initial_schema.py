"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-03 00:00:00
"""
from alembic import op
import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "registrants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("race", sa.String(), nullable=True),
        sa.Column("ethnicity", sa.String(), nullable=True),
        sa.Column("sex", sa.String(), nullable=True),
        sa.Column("height_cm", sa.Integer(), nullable=True),
        sa.Column("weight_kg", sa.Integer(), nullable=True),
        sa.Column("eye_color", sa.String(), nullable=True),
        sa.Column("hair_color", sa.String(), nullable=True),
        sa.Column("risk_level", sa.String(), nullable=True),
        sa.Column("demographics", sa.JSON(), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_registrants_external_id", "registrants", ["external_id"])
    op.create_index("ix_registrants_full_name", "registrants", ["full_name"])

    op.create_table(
        "ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_name", sa.String(), nullable=False),
        sa.Column("source_state", sa.String(length=2), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("registrant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("registrants.id"), nullable=False),
        sa.Column("alias_name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "addresses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("registrant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("registrants.id"), nullable=False),
        sa.Column("line1", sa.String(), nullable=True),
        sa.Column("line2", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("state", sa.String(length=2), nullable=True),
        sa.Column("postal_code", sa.String(), nullable=True),
        sa.Column("county", sa.String(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("address_precision", sa.String(), nullable=True),
        sa.Column("location_geom", geoalchemy2.types.Geometry(geometry_type="POINT", srid=4326), nullable=True),
        sa.Column("location_wkt", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "offenses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("registrant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("registrants.id"), nullable=False),
        sa.Column("offense_name", sa.String(), nullable=False),
        sa.Column("offense_date", sa.Date(), nullable=True),
        sa.Column("conviction_date", sa.Date(), nullable=True),
        sa.Column("disposition", sa.String(), nullable=True),
        sa.Column("statute", sa.String(), nullable=True),
        sa.Column("victim_age", sa.String(), nullable=True),
        sa.Column("victim_gender", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "photos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("registrant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("registrants.id"), nullable=False),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column("sha256", sa.String(), nullable=True),
        sa.Column("content_type", sa.String(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "source_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("registrant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("registrants.id"), nullable=True),
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingestion_runs.id"), nullable=False),
        sa.Column("source_name", sa.String(), nullable=False),
        sa.Column("source_state", sa.String(length=2), nullable=True),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("raw_payload_path", sa.String(), nullable=True),
        sa.Column("raw_html", sa.Text(), nullable=True),
        sa.Column("normalized_payload", sa.JSON(), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("source_records")
    op.drop_table("photos")
    op.drop_table("offenses")
    op.drop_table("addresses")
    op.drop_table("aliases")
    op.drop_table("ingestion_runs")
    op.drop_index("ix_registrants_full_name", table_name="registrants")
    op.drop_index("ix_registrants_external_id", table_name="registrants")
    op.drop_table("registrants")
