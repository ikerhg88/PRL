"""Store approved platform write paths.

Revision ID: 0016_platform_write_paths
Revises: 0015_worker_identifier_unique
Create Date: 2026-05-21 12:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0016_platform_write_paths"
down_revision = "0015_worker_identifier_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_write_paths",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("manifest_id", sa.Integer(), nullable=False),
        sa.Column("account_proposal_id", sa.Integer(), nullable=True),
        sa.Column("external_platform_id", sa.Integer(), nullable=True),
        sa.Column("platform_account_id", sa.Integer(), nullable=True),
        sa.Column("capture_run_id", sa.Integer(), nullable=True),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("entity_scope", sa.String(length=60), nullable=True),
        sa.Column("path_kind", sa.String(length=80), nullable=False),
        sa.Column("path_label", sa.String(length=180), nullable=False),
        sa.Column("host", sa.String(length=240), nullable=True),
        sa.Column("entry_path", sa.String(length=700), nullable=True),
        sa.Column("field_paths_json", sa.JSON(), nullable=False),
        sa.Column("selector_map_json", sa.JSON(), nullable=False),
        sa.Column("readback_paths_json", sa.JSON(), nullable=False),
        sa.Column("source_evidence_ref", sa.String(length=500), nullable=True),
        sa.Column("review_status", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("approval_notes", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_proposal_id"], ["platform_rpa_account_proposals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["capture_run_id"], ["platform_review_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["external_platform_id"], ["external_platforms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["manifest_id"], ["platform_rpa_manifests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["platform_account_id"], ["platform_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "account_proposal_id",
            "operation",
            "path_kind",
            "path_label",
            name="uq_platform_write_path_account_operation_label",
        ),
    )
    op.create_index("ix_platform_write_paths_tenant_id", "platform_write_paths", ["tenant_id"], unique=False)
    op.create_index("ix_platform_write_paths_manifest_id", "platform_write_paths", ["manifest_id"], unique=False)
    op.create_index(
        "ix_platform_write_paths_account_proposal_id",
        "platform_write_paths",
        ["account_proposal_id"],
        unique=False,
    )
    op.create_index("ix_platform_write_paths_external_platform_id", "platform_write_paths", ["external_platform_id"], unique=False)
    op.create_index("ix_platform_write_paths_platform_account_id", "platform_write_paths", ["platform_account_id"], unique=False)
    op.create_index("ix_platform_write_paths_capture_run_id", "platform_write_paths", ["capture_run_id"], unique=False)
    op.create_index("ix_platform_write_paths_operation", "platform_write_paths", ["operation"], unique=False)
    op.create_index("ix_platform_write_paths_entity_scope", "platform_write_paths", ["entity_scope"], unique=False)
    op.create_index("ix_platform_write_paths_path_kind", "platform_write_paths", ["path_kind"], unique=False)
    op.create_index("ix_platform_write_paths_host", "platform_write_paths", ["host"], unique=False)
    op.create_index("ix_platform_write_paths_review_status", "platform_write_paths", ["review_status"], unique=False)
    op.create_index("ix_platform_write_paths_status", "platform_write_paths", ["status"], unique=False)
    op.create_index(
        "ix_platform_write_paths_lookup",
        "platform_write_paths",
        ["tenant_id", "manifest_id", "account_proposal_id", "operation", "review_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_platform_write_paths_lookup", table_name="platform_write_paths")
    op.drop_index("ix_platform_write_paths_status", table_name="platform_write_paths")
    op.drop_index("ix_platform_write_paths_review_status", table_name="platform_write_paths")
    op.drop_index("ix_platform_write_paths_host", table_name="platform_write_paths")
    op.drop_index("ix_platform_write_paths_path_kind", table_name="platform_write_paths")
    op.drop_index("ix_platform_write_paths_entity_scope", table_name="platform_write_paths")
    op.drop_index("ix_platform_write_paths_operation", table_name="platform_write_paths")
    op.drop_index("ix_platform_write_paths_capture_run_id", table_name="platform_write_paths")
    op.drop_index("ix_platform_write_paths_platform_account_id", table_name="platform_write_paths")
    op.drop_index("ix_platform_write_paths_external_platform_id", table_name="platform_write_paths")
    op.drop_index("ix_platform_write_paths_account_proposal_id", table_name="platform_write_paths")
    op.drop_index("ix_platform_write_paths_manifest_id", table_name="platform_write_paths")
    op.drop_index("ix_platform_write_paths_tenant_id", table_name="platform_write_paths")
    op.drop_table("platform_write_paths")
