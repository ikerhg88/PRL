"""Normalize observed platform state.

Revision ID: 0017_platform_observed_state
Revises: 0016_platform_write_paths
Create Date: 2026-05-23 16:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0017_platform_observed_state"
down_revision = "0016_platform_write_paths"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_observed_entities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("manifest_id", sa.Integer(), nullable=False),
        sa.Column("account_proposal_id", sa.Integer(), nullable=True),
        sa.Column("external_platform_id", sa.Integer(), nullable=True),
        sa.Column("platform_account_id", sa.Integer(), nullable=True),
        sa.Column("source_run_id", sa.Integer(), nullable=True),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("local_company_id", sa.Integer(), nullable=True),
        sa.Column("local_worker_id", sa.Integer(), nullable=True),
        sa.Column("external_entity_key", sa.String(length=240), nullable=False),
        sa.Column("external_display_name", sa.String(length=240), nullable=True),
        sa.Column("external_status", sa.String(length=80), nullable=False),
        sa.Column("status_color", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("source_page_label", sa.String(length=180), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["account_proposal_id"], ["platform_rpa_account_proposals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["external_platform_id"], ["external_platforms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["local_company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["local_worker_id"], ["workers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["manifest_id"], ["platform_rpa_manifests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["platform_account_id"], ["platform_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_run_id"], ["platform_review_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "account_proposal_id",
            "entity_type",
            "external_entity_key",
            name="uq_platform_observed_entity_key",
        ),
    )
    op.create_index("ix_platform_observed_entities_tenant_id", "platform_observed_entities", ["tenant_id"], unique=False)
    op.create_index("ix_platform_observed_entities_manifest_id", "platform_observed_entities", ["manifest_id"], unique=False)
    op.create_index(
        "ix_platform_observed_entities_account_proposal_id",
        "platform_observed_entities",
        ["account_proposal_id"],
        unique=False,
    )
    op.create_index(
        "ix_platform_observed_entities_external_platform_id",
        "platform_observed_entities",
        ["external_platform_id"],
        unique=False,
    )
    op.create_index(
        "ix_platform_observed_entities_platform_account_id",
        "platform_observed_entities",
        ["platform_account_id"],
        unique=False,
    )
    op.create_index(
        "ix_platform_observed_entities_source_run_id",
        "platform_observed_entities",
        ["source_run_id"],
        unique=False,
    )
    op.create_index("ix_platform_observed_entities_entity_type", "platform_observed_entities", ["entity_type"], unique=False)
    op.create_index(
        "ix_platform_observed_entities_local_company_id",
        "platform_observed_entities",
        ["local_company_id"],
        unique=False,
    )
    op.create_index(
        "ix_platform_observed_entities_local_worker_id",
        "platform_observed_entities",
        ["local_worker_id"],
        unique=False,
    )
    op.create_index(
        "ix_platform_observed_entities_external_status",
        "platform_observed_entities",
        ["external_status"],
        unique=False,
    )
    op.create_index("ix_platform_observed_entities_observed_at", "platform_observed_entities", ["observed_at"], unique=False)
    op.create_index("ix_platform_observed_entities_last_seen_at", "platform_observed_entities", ["last_seen_at"], unique=False)

    op.create_table(
        "platform_observed_document_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("manifest_id", sa.Integer(), nullable=False),
        sa.Column("account_proposal_id", sa.Integer(), nullable=True),
        sa.Column("external_platform_id", sa.Integer(), nullable=True),
        sa.Column("platform_account_id", sa.Integer(), nullable=True),
        sa.Column("source_run_id", sa.Integer(), nullable=True),
        sa.Column("entity_scope", sa.String(length=40), nullable=False),
        sa.Column("local_company_id", sa.Integer(), nullable=True),
        sa.Column("local_worker_id", sa.Integer(), nullable=True),
        sa.Column("document_type_id", sa.Integer(), nullable=True),
        sa.Column("matched_document_id", sa.Integer(), nullable=True),
        sa.Column("matched_document_version_id", sa.Integer(), nullable=True),
        sa.Column("external_requirement_key", sa.String(length=320), nullable=False),
        sa.Column("external_requirement_label", sa.String(length=240), nullable=False),
        sa.Column("external_entity_label", sa.String(length=240), nullable=True),
        sa.Column("external_status", sa.String(length=80), nullable=False),
        sa.Column("status_color", sa.String(length=20), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("external_comment", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_expires_at", sa.Date(), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("source_page_label", sa.String(length=180), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["account_proposal_id"], ["platform_rpa_account_proposals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_type_id"], ["document_types.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["external_platform_id"], ["external_platforms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["local_company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["local_worker_id"], ["workers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["manifest_id"], ["platform_rpa_manifests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matched_document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["matched_document_version_id"], ["document_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["platform_account_id"], ["platform_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_run_id"], ["platform_review_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "account_proposal_id",
            "external_requirement_key",
            name="uq_platform_observed_document_request_key",
        ),
    )
    op.create_index(
        "ix_platform_observed_document_requests_tenant_id",
        "platform_observed_document_requests",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_platform_observed_document_requests_manifest_id",
        "platform_observed_document_requests",
        ["manifest_id"],
        unique=False,
    )
    op.create_index(
        "ix_platform_observed_document_requests_account_proposal_id",
        "platform_observed_document_requests",
        ["account_proposal_id"],
        unique=False,
    )
    op.create_index(
        "ix_platform_observed_document_requests_external_platform_id",
        "platform_observed_document_requests",
        ["external_platform_id"],
        unique=False,
    )
    op.create_index(
        "ix_platform_observed_document_requests_platform_account_id",
        "platform_observed_document_requests",
        ["platform_account_id"],
        unique=False,
    )
    op.create_index(
        "ix_platform_observed_document_requests_source_run_id",
        "platform_observed_document_requests",
        ["source_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_platform_observed_document_requests_entity_scope",
        "platform_observed_document_requests",
        ["entity_scope"],
        unique=False,
    )
    op.create_index(
        "ix_platform_observed_document_requests_local_company_id",
        "platform_observed_document_requests",
        ["local_company_id"],
        unique=False,
    )
    op.create_index(
        "ix_platform_observed_document_requests_local_worker_id",
        "platform_observed_document_requests",
        ["local_worker_id"],
        unique=False,
    )
    op.create_index(
        "ix_platform_observed_document_requests_document_type_id",
        "platform_observed_document_requests",
        ["document_type_id"],
        unique=False,
    )
    op.create_index(
        "ix_platform_observed_document_requests_matched_document_id",
        "platform_observed_document_requests",
        ["matched_document_id"],
        unique=False,
    )
    op.create_index(
        "ix_platform_observed_document_requests_matched_document_version_id",
        "platform_observed_document_requests",
        ["matched_document_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_platform_observed_document_requests_external_status",
        "platform_observed_document_requests",
        ["external_status"],
        unique=False,
    )
    op.create_index(
        "ix_platform_observed_document_requests_severity",
        "platform_observed_document_requests",
        ["severity"],
        unique=False,
    )
    op.create_index(
        "ix_platform_observed_document_requests_external_expires_at",
        "platform_observed_document_requests",
        ["external_expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_platform_observed_document_requests_observed_at",
        "platform_observed_document_requests",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        "ix_platform_observed_document_requests_last_seen_at",
        "platform_observed_document_requests",
        ["last_seen_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_platform_observed_document_requests_last_seen_at", table_name="platform_observed_document_requests")
    op.drop_index("ix_platform_observed_document_requests_observed_at", table_name="platform_observed_document_requests")
    op.drop_index("ix_platform_observed_document_requests_external_expires_at", table_name="platform_observed_document_requests")
    op.drop_index("ix_platform_observed_document_requests_severity", table_name="platform_observed_document_requests")
    op.drop_index("ix_platform_observed_document_requests_external_status", table_name="platform_observed_document_requests")
    op.drop_index(
        "ix_platform_observed_document_requests_matched_document_version_id",
        table_name="platform_observed_document_requests",
    )
    op.drop_index("ix_platform_observed_document_requests_matched_document_id", table_name="platform_observed_document_requests")
    op.drop_index("ix_platform_observed_document_requests_document_type_id", table_name="platform_observed_document_requests")
    op.drop_index("ix_platform_observed_document_requests_local_worker_id", table_name="platform_observed_document_requests")
    op.drop_index("ix_platform_observed_document_requests_local_company_id", table_name="platform_observed_document_requests")
    op.drop_index("ix_platform_observed_document_requests_entity_scope", table_name="platform_observed_document_requests")
    op.drop_index("ix_platform_observed_document_requests_source_run_id", table_name="platform_observed_document_requests")
    op.drop_index("ix_platform_observed_document_requests_platform_account_id", table_name="platform_observed_document_requests")
    op.drop_index("ix_platform_observed_document_requests_external_platform_id", table_name="platform_observed_document_requests")
    op.drop_index("ix_platform_observed_document_requests_account_proposal_id", table_name="platform_observed_document_requests")
    op.drop_index("ix_platform_observed_document_requests_manifest_id", table_name="platform_observed_document_requests")
    op.drop_index("ix_platform_observed_document_requests_tenant_id", table_name="platform_observed_document_requests")
    op.drop_table("platform_observed_document_requests")

    op.drop_index("ix_platform_observed_entities_last_seen_at", table_name="platform_observed_entities")
    op.drop_index("ix_platform_observed_entities_observed_at", table_name="platform_observed_entities")
    op.drop_index("ix_platform_observed_entities_external_status", table_name="platform_observed_entities")
    op.drop_index("ix_platform_observed_entities_local_worker_id", table_name="platform_observed_entities")
    op.drop_index("ix_platform_observed_entities_local_company_id", table_name="platform_observed_entities")
    op.drop_index("ix_platform_observed_entities_entity_type", table_name="platform_observed_entities")
    op.drop_index("ix_platform_observed_entities_source_run_id", table_name="platform_observed_entities")
    op.drop_index("ix_platform_observed_entities_platform_account_id", table_name="platform_observed_entities")
    op.drop_index("ix_platform_observed_entities_external_platform_id", table_name="platform_observed_entities")
    op.drop_index("ix_platform_observed_entities_account_proposal_id", table_name="platform_observed_entities")
    op.drop_index("ix_platform_observed_entities_manifest_id", table_name="platform_observed_entities")
    op.drop_index("ix_platform_observed_entities_tenant_id", table_name="platform_observed_entities")
    op.drop_table("platform_observed_entities")
