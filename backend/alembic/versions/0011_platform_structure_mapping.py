"""platform structure mapping

Revision ID: 0011_platform_structure_mapping
Revises: 0010_document_platform_expiry
Create Date: 2026-05-18
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011_platform_structure_mapping"
down_revision: Union[str, None] = "0010_document_platform_expiry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_structure_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("external_platform_id", sa.Integer(), nullable=True),
        sa.Column("platform_account_id", sa.Integer(), nullable=True),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("platform_label", sa.String(length=180), nullable=False),
        sa.Column("host", sa.String(length=240), nullable=True),
        sa.Column("login_status", sa.String(length=80), nullable=True),
        sa.Column("source_type", sa.String(length=60), nullable=False, server_default="readonly_capture"),
        sa.Column("source_ref", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=60), nullable=False, server_default="mapped"),
        sa.Column("structure_json", sa.JSON(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["external_platform_id"], ["external_platforms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["platform_account_id"], ["platform_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platform_structure_snapshots_company_id", "platform_structure_snapshots", ["company_id"])
    op.create_index(
        "ix_platform_structure_snapshots_external_platform_id",
        "platform_structure_snapshots",
        ["external_platform_id"],
    )
    op.create_index("ix_platform_structure_snapshots_host", "platform_structure_snapshots", ["host"])
    op.create_index("ix_platform_structure_snapshots_login_status", "platform_structure_snapshots", ["login_status"])
    op.create_index(
        "ix_platform_structure_snapshots_platform_account_id",
        "platform_structure_snapshots",
        ["platform_account_id"],
    )
    op.create_index("ix_platform_structure_snapshots_tenant_id", "platform_structure_snapshots", ["tenant_id"])

    op.create_table(
        "platform_discovered_labels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("external_platform_id", sa.Integer(), nullable=True),
        sa.Column("platform_account_id", sa.Integer(), nullable=True),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("label_kind", sa.String(length=60), nullable=False),
        sa.Column("raw_label", sa.String(length=300), nullable=False),
        sa.Column("normalized_label", sa.String(length=300), nullable=False),
        sa.Column("page_label", sa.String(length=180), nullable=True),
        sa.Column("entity_scope", sa.String(length=60), nullable=True),
        sa.Column("standard_key", sa.String(length=120), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_status", sa.String(length=60), nullable=False, server_default="proposed"),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["external_platform_id"], ["external_platforms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["platform_account_id"], ["platform_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["platform_structure_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platform_discovered_labels_company_id", "platform_discovered_labels", ["company_id"])
    op.create_index(
        "ix_platform_discovered_labels_entity_scope",
        "platform_discovered_labels",
        ["entity_scope"],
    )
    op.create_index(
        "ix_platform_discovered_labels_external_platform_id",
        "platform_discovered_labels",
        ["external_platform_id"],
    )
    op.create_index("ix_platform_discovered_labels_label_kind", "platform_discovered_labels", ["label_kind"])
    op.create_index(
        "ix_platform_discovered_labels_normalized_label",
        "platform_discovered_labels",
        ["normalized_label"],
    )
    op.create_index(
        "ix_platform_discovered_labels_platform_account_id",
        "platform_discovered_labels",
        ["platform_account_id"],
    )
    op.create_index("ix_platform_discovered_labels_review_status", "platform_discovered_labels", ["review_status"])
    op.create_index("ix_platform_discovered_labels_snapshot_id", "platform_discovered_labels", ["snapshot_id"])
    op.create_index("ix_platform_discovered_labels_standard_key", "platform_discovered_labels", ["standard_key"])
    op.create_index("ix_platform_discovered_labels_tenant_id", "platform_discovered_labels", ["tenant_id"])
    op.create_index(
        "ix_platform_discovered_labels_tenant_standard",
        "platform_discovered_labels",
        ["tenant_id", "standard_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_platform_discovered_labels_tenant_standard", table_name="platform_discovered_labels")
    op.drop_index("ix_platform_discovered_labels_tenant_id", table_name="platform_discovered_labels")
    op.drop_index("ix_platform_discovered_labels_standard_key", table_name="platform_discovered_labels")
    op.drop_index("ix_platform_discovered_labels_snapshot_id", table_name="platform_discovered_labels")
    op.drop_index("ix_platform_discovered_labels_review_status", table_name="platform_discovered_labels")
    op.drop_index("ix_platform_discovered_labels_platform_account_id", table_name="platform_discovered_labels")
    op.drop_index("ix_platform_discovered_labels_normalized_label", table_name="platform_discovered_labels")
    op.drop_index("ix_platform_discovered_labels_label_kind", table_name="platform_discovered_labels")
    op.drop_index("ix_platform_discovered_labels_external_platform_id", table_name="platform_discovered_labels")
    op.drop_index("ix_platform_discovered_labels_entity_scope", table_name="platform_discovered_labels")
    op.drop_index("ix_platform_discovered_labels_company_id", table_name="platform_discovered_labels")
    op.drop_table("platform_discovered_labels")

    op.drop_index("ix_platform_structure_snapshots_tenant_id", table_name="platform_structure_snapshots")
    op.drop_index("ix_platform_structure_snapshots_platform_account_id", table_name="platform_structure_snapshots")
    op.drop_index("ix_platform_structure_snapshots_login_status", table_name="platform_structure_snapshots")
    op.drop_index("ix_platform_structure_snapshots_host", table_name="platform_structure_snapshots")
    op.drop_index("ix_platform_structure_snapshots_external_platform_id", table_name="platform_structure_snapshots")
    op.drop_index("ix_platform_structure_snapshots_company_id", table_name="platform_structure_snapshots")
    op.drop_table("platform_structure_snapshots")
