"""registry sources inventory

Revision ID: 0002_registry_sources
Revises: 0001_initial_schema
Create Date: 2026-07-04 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_registry_sources"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "registry_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("jurisdiction_type", sa.String(), nullable=False),
        sa.Column("official_registry_url", sa.String(), nullable=False),
        sa.Column("access_surface", sa.String(), nullable=False),
        sa.Column("recommended_acquisition_path", sa.String(), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("source_directory_name", sa.String(), nullable=False),
        sa.Column("source_directory_url", sa.String(), nullable=False),
        sa.Column("source_checked_on", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("state", "jurisdiction_type", name="uq_registry_sources_state_jurisdiction"),
    )
    op.create_index("ix_registry_sources_state", "registry_sources", ["state"])
    op.create_index("ix_registry_sources_jurisdiction_type", "registry_sources", ["jurisdiction_type"])
    op.create_index("ix_registry_sources_access_surface", "registry_sources", ["access_surface"])


def downgrade() -> None:
    op.drop_index("ix_registry_sources_access_surface", table_name="registry_sources")
    op.drop_index("ix_registry_sources_jurisdiction_type", table_name="registry_sources")
    op.drop_index("ix_registry_sources_state", table_name="registry_sources")
    op.drop_table("registry_sources")
