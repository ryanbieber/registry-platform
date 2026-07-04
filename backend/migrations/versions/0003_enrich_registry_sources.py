"""enrich registry sources

Revision ID: 0003_enrich_registry_sources
Revises: 0002_registry_sources
Create Date: 2026-07-04 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_enrich_registry_sources"
down_revision = "0002_registry_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("registry_sources", sa.Column("state_code", sa.String(length=2), nullable=True))
    op.add_column("registry_sources", sa.Column("registry_http_status", sa.Integer(), nullable=True))
    op.add_column("registry_sources", sa.Column("final_registry_url", sa.String(), nullable=True))
    op.add_column("registry_sources", sa.Column("registry_host", sa.String(), nullable=True))
    op.add_column("registry_sources", sa.Column("registry_page_title", sa.String(), nullable=True))
    op.add_column("registry_sources", sa.Column("registry_content_type", sa.String(), nullable=True))
    op.add_column("registry_sources", sa.Column("vendor_name", sa.String(), nullable=True))
    op.add_column("registry_sources", sa.Column("robots_txt_url", sa.String(), nullable=True))
    op.add_column("registry_sources", sa.Column("robots_txt_status", sa.Integer(), nullable=True))
    op.add_column("registry_sources", sa.Column("metadata_retrieved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("registry_sources", sa.Column("metadata_error", sa.String(), nullable=True))

    op.create_index("ix_registry_sources_state_code", "registry_sources", ["state_code"])
    op.create_index("ix_registry_sources_registry_http_status", "registry_sources", ["registry_http_status"])
    op.create_index("ix_registry_sources_registry_host", "registry_sources", ["registry_host"])
    op.create_index("ix_registry_sources_vendor_name", "registry_sources", ["vendor_name"])


def downgrade() -> None:
    op.drop_index("ix_registry_sources_vendor_name", table_name="registry_sources")
    op.drop_index("ix_registry_sources_registry_host", table_name="registry_sources")
    op.drop_index("ix_registry_sources_registry_http_status", table_name="registry_sources")
    op.drop_index("ix_registry_sources_state_code", table_name="registry_sources")

    op.drop_column("registry_sources", "metadata_error")
    op.drop_column("registry_sources", "metadata_retrieved_at")
    op.drop_column("registry_sources", "robots_txt_status")
    op.drop_column("registry_sources", "robots_txt_url")
    op.drop_column("registry_sources", "vendor_name")
    op.drop_column("registry_sources", "registry_content_type")
    op.drop_column("registry_sources", "registry_page_title")
    op.drop_column("registry_sources", "registry_host")
    op.drop_column("registry_sources", "final_registry_url")
    op.drop_column("registry_sources", "registry_http_status")
    op.drop_column("registry_sources", "state_code")
