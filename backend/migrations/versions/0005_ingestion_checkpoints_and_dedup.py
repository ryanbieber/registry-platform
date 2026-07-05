"""ingestion checkpoints and source record deduping

Revision ID: 0005_ingestion_checkpoints_and_dedup
Revises: 0004_address_supporting_information
Create Date: 2026-07-04 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0005_ingestion_checkpoints_and_dedup"
down_revision = "0004_address_supporting_information"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_source_records_source_name_external_id",
        "source_records",
        ["source_name", "external_id"],
    )

    op.create_table(
        "ingestion_checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_name", sa.String(), nullable=False),
        sa.Column("source_state", sa.String(length=2), nullable=True),
        sa.Column("checkpoint_name", sa.String(), nullable=False),
        sa.Column("cursor", sa.String(), nullable=True),
        sa.Column("last_external_id", sa.String(), nullable=True),
        sa.Column("last_ingestion_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingestion_runs.id"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_name",
            "source_state",
            "checkpoint_name",
            name="uq_ingestion_checkpoints_source_state_name",
        ),
    )
    op.create_index("ix_ingestion_checkpoints_source_name", "ingestion_checkpoints", ["source_name"])
    op.create_index("ix_ingestion_checkpoints_source_state", "ingestion_checkpoints", ["source_state"])
    op.create_index("ix_ingestion_checkpoints_checkpoint_name", "ingestion_checkpoints", ["checkpoint_name"])
    op.create_index("ix_ingestion_checkpoints_last_external_id", "ingestion_checkpoints", ["last_external_id"])
    op.create_index("ix_ingestion_checkpoints_last_ingestion_run_id", "ingestion_checkpoints", ["last_ingestion_run_id"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_checkpoints_last_ingestion_run_id", table_name="ingestion_checkpoints")
    op.drop_index("ix_ingestion_checkpoints_last_external_id", table_name="ingestion_checkpoints")
    op.drop_index("ix_ingestion_checkpoints_checkpoint_name", table_name="ingestion_checkpoints")
    op.drop_index("ix_ingestion_checkpoints_source_state", table_name="ingestion_checkpoints")
    op.drop_index("ix_ingestion_checkpoints_source_name", table_name="ingestion_checkpoints")
    op.drop_table("ingestion_checkpoints")
    op.drop_constraint("uq_source_records_source_name_external_id", "source_records", type_="unique")
