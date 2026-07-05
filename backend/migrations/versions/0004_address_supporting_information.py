"""address supporting information

Revision ID: 0004_address_supporting_information
Revises: 0003_enrich_registry_sources
Create Date: 2026-07-04 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0004_address_supporting_information"
down_revision = "0003_enrich_registry_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "address_enrichments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("address_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("addresses.id"), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("address_id", "provider", name="uq_address_enrichments_address_provider"),
    )
    op.create_index("ix_address_enrichments_address_id", "address_enrichments", ["address_id"])
    op.create_index("ix_address_enrichments_provider", "address_enrichments", ["provider"])
    op.create_index("ix_address_enrichments_status", "address_enrichments", ["status"])

    op.create_table(
        "census_geographies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("address_enrichment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("address_enrichments.id"), nullable=False),
        sa.Column("matched_address", sa.String(), nullable=True),
        sa.Column("matched_latitude", sa.Float(), nullable=True),
        sa.Column("matched_longitude", sa.Float(), nullable=True),
        sa.Column("state_abbr", sa.String(length=2), nullable=True),
        sa.Column("state_fips", sa.String(length=2), nullable=True),
        sa.Column("county_fips", sa.String(length=5), nullable=True),
        sa.Column("county_name", sa.String(), nullable=True),
        sa.Column("tract", sa.String(), nullable=True),
        sa.Column("tract_geoid", sa.String(), nullable=True),
        sa.Column("block_group", sa.String(), nullable=True),
        sa.Column("block_group_geoid", sa.String(), nullable=True),
        sa.Column("benchmark", sa.String(), nullable=True),
        sa.Column("vintage", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("address_enrichment_id", name="uq_census_geographies_address_enrichment"),
    )
    op.create_index("ix_census_geographies_address_enrichment_id", "census_geographies", ["address_enrichment_id"])
    op.create_index("ix_census_geographies_state_abbr", "census_geographies", ["state_abbr"])
    op.create_index("ix_census_geographies_county_fips", "census_geographies", ["county_fips"])
    op.create_index("ix_census_geographies_tract_geoid", "census_geographies", ["tract_geoid"])

    op.create_table(
        "crime_contexts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("address_enrichment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("address_enrichments.id"), nullable=False),
        sa.Column("state_abbr", sa.String(length=2), nullable=True),
        sa.Column("state_name", sa.String(), nullable=True),
        sa.Column("current_year", sa.Integer(), nullable=True),
        sa.Column("population", sa.Integer(), nullable=True),
        sa.Column("violent_crime", sa.Integer(), nullable=True),
        sa.Column("homicide", sa.Integer(), nullable=True),
        sa.Column("rape_legacy", sa.Integer(), nullable=True),
        sa.Column("rape_revised", sa.Integer(), nullable=True),
        sa.Column("robbery", sa.Integer(), nullable=True),
        sa.Column("aggravated_assault", sa.Integer(), nullable=True),
        sa.Column("property_crime", sa.Integer(), nullable=True),
        sa.Column("burglary", sa.Integer(), nullable=True),
        sa.Column("larceny", sa.Integer(), nullable=True),
        sa.Column("motor_vehicle_theft", sa.Integer(), nullable=True),
        sa.Column("total_agencies", sa.Integer(), nullable=True),
        sa.Column("participating_agencies", sa.Integer(), nullable=True),
        sa.Column("participation_pct", sa.Float(), nullable=True),
        sa.Column("nibrs_participating_agencies", sa.Integer(), nullable=True),
        sa.Column("nibrs_participation_pct", sa.Float(), nullable=True),
        sa.Column("participating_population", sa.Integer(), nullable=True),
        sa.Column("participating_population_pct", sa.Float(), nullable=True),
        sa.Column("caveats", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("address_enrichment_id", name="uq_crime_contexts_address_enrichment"),
    )
    op.create_index("ix_crime_contexts_address_enrichment_id", "crime_contexts", ["address_enrichment_id"])
    op.create_index("ix_crime_contexts_state_abbr", "crime_contexts", ["state_abbr"])
    op.create_index("ix_crime_contexts_current_year", "crime_contexts", ["current_year"])


def downgrade() -> None:
    op.drop_index("ix_crime_contexts_current_year", table_name="crime_contexts")
    op.drop_index("ix_crime_contexts_state_abbr", table_name="crime_contexts")
    op.drop_index("ix_crime_contexts_address_enrichment_id", table_name="crime_contexts")
    op.drop_table("crime_contexts")

    op.drop_index("ix_census_geographies_tract_geoid", table_name="census_geographies")
    op.drop_index("ix_census_geographies_county_fips", table_name="census_geographies")
    op.drop_index("ix_census_geographies_state_abbr", table_name="census_geographies")
    op.drop_index("ix_census_geographies_address_enrichment_id", table_name="census_geographies")
    op.drop_table("census_geographies")

    op.drop_index("ix_address_enrichments_status", table_name="address_enrichments")
    op.drop_index("ix_address_enrichments_provider", table_name="address_enrichments")
    op.drop_index("ix_address_enrichments_address_id", table_name="address_enrichments")
    op.drop_table("address_enrichments")
