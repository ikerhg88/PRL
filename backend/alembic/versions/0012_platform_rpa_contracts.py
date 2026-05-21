"""platform rpa contracts

Revision ID: 0012_platform_rpa_contracts
Revises: 0011_platform_structure_mapping
Create Date: 2026-05-18
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_platform_rpa_contracts"
down_revision: Union[str, None] = "0011_platform_structure_mapping"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_rpa_manifests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("external_platform_id", sa.Integer(), nullable=True),
        sa.Column("platform_slug", sa.String(length=120), nullable=False),
        sa.Column("platform_name", sa.String(length=180), nullable=False),
        sa.Column("family", sa.String(length=120), nullable=True),
        sa.Column("mode", sa.String(length=80), nullable=False, server_default="authorized_rpa"),
        sa.Column("status", sa.String(length=80), nullable=False, server_default="proposal_disabled"),
        sa.Column("priority_group", sa.String(length=80), nullable=True),
        sa.Column("source_ref", sa.String(length=500), nullable=True),
        sa.Column("schema_version", sa.String(length=40), nullable=True),
        sa.Column("generated_at", sa.String(length=40), nullable=True),
        sa.Column("hosts", sa.JSON(), nullable=False),
        sa.Column("entry_urls", sa.JSON(), nullable=False),
        sa.Column("allowed_operations", sa.JSON(), nullable=False),
        sa.Column("allowed_entity_types", sa.JSON(), nullable=False),
        sa.Column("requires_signed_authorization", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("dry_run_default", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("manual_approval_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("rpa_assisted_on_control", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "sensitive_data_minimization_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "auxiliary_platform_review_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["external_platform_id"], ["external_platforms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "platform_slug", name="uq_platform_rpa_manifest_tenant_slug"),
    )
    op.create_index("ix_platform_rpa_manifests_external_platform_id", "platform_rpa_manifests", ["external_platform_id"])
    op.create_index("ix_platform_rpa_manifests_platform_slug", "platform_rpa_manifests", ["platform_slug"])
    op.create_index("ix_platform_rpa_manifests_priority_group", "platform_rpa_manifests", ["priority_group"])
    op.create_index("ix_platform_rpa_manifests_status", "platform_rpa_manifests", ["status"])
    op.create_index("ix_platform_rpa_manifests_tenant_id", "platform_rpa_manifests", ["tenant_id"])

    op.create_table(
        "platform_rpa_account_proposals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("manifest_id", sa.Integer(), nullable=False),
        sa.Column("external_platform_id", sa.Integer(), nullable=True),
        sa.Column("platform_account_id", sa.Integer(), nullable=True),
        sa.Column("source_platform_account_id", sa.String(length=180), nullable=False),
        sa.Column("company_source_label", sa.String(length=80), nullable=True),
        sa.Column("source_excel_sheet", sa.String(length=80), nullable=True),
        sa.Column("source_excel_row", sa.Integer(), nullable=True),
        sa.Column("external_company_name", sa.String(length=240), nullable=True),
        sa.Column("entry_url", sa.String(length=500), nullable=True),
        sa.Column("host", sa.String(length=240), nullable=True),
        sa.Column("user_hint_masked", sa.String(length=180), nullable=True),
        sa.Column("credential_secret_ref", sa.String(length=320), nullable=True),
        sa.Column("account_status", sa.String(length=80), nullable=False, server_default="active_in_source"),
        sa.Column("status", sa.String(length=80), nullable=False, server_default="proposal_disabled"),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("manual_approval_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allowed_operations", sa.JSON(), nullable=False),
        sa.Column("allowed_entity_types", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["external_platform_id"], ["external_platforms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["manifest_id"], ["platform_rpa_manifests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["platform_account_id"], ["platform_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "source_platform_account_id",
            name="uq_platform_rpa_account_tenant_source",
        ),
    )
    op.create_index(
        "ix_platform_rpa_account_proposals_company_source_label",
        "platform_rpa_account_proposals",
        ["company_source_label"],
    )
    op.create_index(
        "ix_platform_rpa_account_proposals_external_platform_id",
        "platform_rpa_account_proposals",
        ["external_platform_id"],
    )
    op.create_index("ix_platform_rpa_account_proposals_host", "platform_rpa_account_proposals", ["host"])
    op.create_index(
        "ix_platform_rpa_account_proposals_manifest_id",
        "platform_rpa_account_proposals",
        ["manifest_id"],
    )
    op.create_index(
        "ix_platform_rpa_account_proposals_platform_account_id",
        "platform_rpa_account_proposals",
        ["platform_account_id"],
    )
    op.create_index("ix_platform_rpa_account_proposals_status", "platform_rpa_account_proposals", ["status"])
    op.create_index("ix_platform_rpa_account_proposals_tenant_id", "platform_rpa_account_proposals", ["tenant_id"])

    op.create_table(
        "platform_rpa_mapping_proposals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("manifest_id", sa.Integer(), nullable=False),
        sa.Column("external_platform_id", sa.Integer(), nullable=True),
        sa.Column("mapping_kind", sa.String(length=60), nullable=False),
        sa.Column("entity_scope", sa.String(length=60), nullable=True),
        sa.Column("iker_key", sa.String(length=180), nullable=False),
        sa.Column("external_label", sa.String(length=300), nullable=True),
        sa.Column("external_catalog_value", sa.String(length=240), nullable=True),
        sa.Column("requirement", sa.String(length=120), nullable=True),
        sa.Column("applies_to", sa.String(length=160), nullable=True),
        sa.Column("review_status", sa.String(length=80), nullable=False, server_default="pending_review"),
        sa.Column(
            "status",
            sa.String(length=80),
            nullable=False,
            server_default="proposed_pending_platform_validation",
        ),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["external_platform_id"], ["external_platforms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["manifest_id"], ["platform_rpa_manifests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_platform_rpa_mapping_proposals_entity_scope",
        "platform_rpa_mapping_proposals",
        ["entity_scope"],
    )
    op.create_index(
        "ix_platform_rpa_mapping_proposals_external_platform_id",
        "platform_rpa_mapping_proposals",
        ["external_platform_id"],
    )
    op.create_index("ix_platform_rpa_mapping_proposals_iker_key", "platform_rpa_mapping_proposals", ["iker_key"])
    op.create_index(
        "ix_platform_rpa_mapping_proposals_manifest_id",
        "platform_rpa_mapping_proposals",
        ["manifest_id"],
    )
    op.create_index(
        "ix_platform_rpa_mapping_proposals_mapping_kind",
        "platform_rpa_mapping_proposals",
        ["mapping_kind"],
    )
    op.create_index(
        "ix_platform_rpa_mapping_proposals_review_status",
        "platform_rpa_mapping_proposals",
        ["review_status"],
    )
    op.create_index("ix_platform_rpa_mapping_proposals_tenant_id", "platform_rpa_mapping_proposals", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_platform_rpa_mapping_proposals_tenant_id", table_name="platform_rpa_mapping_proposals")
    op.drop_index("ix_platform_rpa_mapping_proposals_review_status", table_name="platform_rpa_mapping_proposals")
    op.drop_index("ix_platform_rpa_mapping_proposals_mapping_kind", table_name="platform_rpa_mapping_proposals")
    op.drop_index("ix_platform_rpa_mapping_proposals_manifest_id", table_name="platform_rpa_mapping_proposals")
    op.drop_index("ix_platform_rpa_mapping_proposals_iker_key", table_name="platform_rpa_mapping_proposals")
    op.drop_index("ix_platform_rpa_mapping_proposals_external_platform_id", table_name="platform_rpa_mapping_proposals")
    op.drop_index("ix_platform_rpa_mapping_proposals_entity_scope", table_name="platform_rpa_mapping_proposals")
    op.drop_table("platform_rpa_mapping_proposals")

    op.drop_index("ix_platform_rpa_account_proposals_tenant_id", table_name="platform_rpa_account_proposals")
    op.drop_index("ix_platform_rpa_account_proposals_status", table_name="platform_rpa_account_proposals")
    op.drop_index("ix_platform_rpa_account_proposals_platform_account_id", table_name="platform_rpa_account_proposals")
    op.drop_index("ix_platform_rpa_account_proposals_manifest_id", table_name="platform_rpa_account_proposals")
    op.drop_index("ix_platform_rpa_account_proposals_host", table_name="platform_rpa_account_proposals")
    op.drop_index("ix_platform_rpa_account_proposals_external_platform_id", table_name="platform_rpa_account_proposals")
    op.drop_index("ix_platform_rpa_account_proposals_company_source_label", table_name="platform_rpa_account_proposals")
    op.drop_table("platform_rpa_account_proposals")

    op.drop_index("ix_platform_rpa_manifests_tenant_id", table_name="platform_rpa_manifests")
    op.drop_index("ix_platform_rpa_manifests_status", table_name="platform_rpa_manifests")
    op.drop_index("ix_platform_rpa_manifests_priority_group", table_name="platform_rpa_manifests")
    op.drop_index("ix_platform_rpa_manifests_platform_slug", table_name="platform_rpa_manifests")
    op.drop_index("ix_platform_rpa_manifests_external_platform_id", table_name="platform_rpa_manifests")
    op.drop_table("platform_rpa_manifests")
