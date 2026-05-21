"""initial mvp schema

Revision ID: 0001_initial_platform_catalog
Revises:
Create Date: 2026-05-16
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial_platform_catalog"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("tax_id", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        *_timestamps(),
        sa.UniqueConstraint("tax_id", name="uq_tenants_tax_id"),
    )
    op.create_table(
        "external_platforms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("platform_key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="cataloged"),
        sa.Column("is_commercial", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("platform_key", name="uq_external_platforms_platform_key"),
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=240), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=True),
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("tax_id", sa.String(length=40), nullable=True),
        sa.Column("company_type", sa.String(length=40), nullable=False, server_default="contractor"),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "tax_id", name="uq_companies_tenant_tax_id"),
    )
    op.create_index("ix_companies_tenant_id", "companies", ["tenant_id"])
    op.create_table(
        "document_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("entity_scope", sa.String(length=40), nullable=False),
        sa.Column("is_common_cae_type", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("requires_expiration", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("default_validity_days", sa.Integer(), nullable=True),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_document_types_tenant_code"),
    )
    op.create_index("ix_document_types_tenant_id", "document_types", ["tenant_id"])
    op.create_table(
        "work_centers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("risk_profile_id", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_work_centers_tenant_id", "work_centers", ["tenant_id"])
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("client_company_id", sa.Integer(), nullable=True),
        sa.Column("work_center_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("activity_code", sa.String(length=80), nullable=True),
        sa.Column("starts_at", sa.Date(), nullable=True),
        sa.Column("ends_at", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["work_center_id"], ["work_centers.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_projects_tenant_id", "projects", ["tenant_id"])
    op.create_table(
        "workers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("first_name", sa.String(length=120), nullable=False),
        sa.Column("last_name", sa.String(length=160), nullable=False),
        sa.Column("identifier_type", sa.String(length=40), nullable=True),
        sa.Column("identifier_hash", sa.String(length=128), nullable=True),
        sa.Column("identifier_last4", sa.String(length=4), nullable=True),
        sa.Column("nationality", sa.String(length=80), nullable=True),
        sa.Column("work_position", sa.String(length=160), nullable=True),
        sa.Column("employment_status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column("medical_fitness_status", sa.String(length=60), nullable=True),
        sa.Column("medical_fitness_expires_at", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_workers_tenant_id", "workers", ["tenant_id"])
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("asset_type", sa.String(length=40), nullable=False),
        sa.Column("brand", sa.String(length=120), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("serial_number", sa.String(length=120), nullable=True),
        sa.Column("plate_number", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_assets_tenant_id", "assets", ["tenant_id"])
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("document_type_id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("current_version_id", sa.Integer(), nullable=True),
        sa.Column("status_internal", sa.String(length=60), nullable=False, server_default="draft"),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_type_id"], ["document_types.id"]),
    )
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])
    op.create_table(
        "document_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("file_storage_key", sa.String(length=320), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=240), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False, server_default="application/octet-stream"),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("issued_at", sa.Date(), nullable=True),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False, server_default="manual"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("document_id", "version_number", name="uq_document_versions_number"),
    )
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])
    op.create_index("ix_document_versions_sha256", "document_versions", ["sha256"])
    op.create_index("ix_document_versions_expires_at", "document_versions", ["expires_at"])
    op.create_table(
        "validations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_version_id", sa.Integer(), nullable=False),
        sa.Column("validator_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=60), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["validator_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_table(
        "requirement_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("client_company_id", sa.Integer(), nullable=True),
        sa.Column("work_center_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("activity_code", sa.String(length=80), nullable=True),
        sa.Column("risk_level", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["work_center_id"], ["work_centers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_requirement_profiles_tenant_id", "requirement_profiles", ["tenant_id"])
    op.create_table(
        "document_requirements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("document_type_id", sa.Integer(), nullable=False),
        sa.Column("entity_scope", sa.String(length=40), nullable=False),
        sa.Column("mandatory", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("blocks_access", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("requires_human_validation", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("expiration_warning_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("validity_rule", sa.String(length=120), nullable=True),
        sa.Column("platform_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["profile_id"], ["requirement_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_type_id"], ["document_types.id"]),
        sa.ForeignKeyConstraint(["platform_id"], ["external_platforms.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_document_requirements_profile_id", "document_requirements", ["profile_id"])
    op.create_table(
        "platform_connection_methods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_platform_id", sa.Integer(), nullable=False),
        sa.Column("method_key", sa.String(length=80), nullable=False),
        sa.Column("connector_type", sa.String(length=40), nullable=False),
        sa.Column("connector_key", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=60), nullable=False),
        sa.Column("implemented", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("dry_run_supported", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("manual_approval_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["external_platform_id"], ["external_platforms.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "external_platform_id",
            "method_key",
            name="uq_platform_connection_methods_platform_method",
        ),
    )
    op.create_index(
        "ix_platform_connection_methods_connector_key",
        "platform_connection_methods",
        ["connector_key"],
    )
    op.create_table(
        "platform_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("external_platform_id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=180), nullable=False),
        sa.Column("auth_type", sa.String(length=60), nullable=False, server_default="manual"),
        sa.Column("encrypted_secret_ref", sa.String(length=240), nullable=True),
        sa.Column("mode", sa.String(length=40), nullable=False, server_default="disabled"),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("manual_approval_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["external_platform_id"], ["external_platforms.id"]),
    )
    op.create_index("ix_platform_accounts_tenant_id", "platform_accounts", ["tenant_id"])
    op.create_table(
        "platform_entity_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("external_platform_id", sa.Integer(), nullable=False),
        sa.Column("local_entity_type", sa.String(length=40), nullable=False),
        sa.Column("local_entity_id", sa.Integer(), nullable=False),
        sa.Column("external_entity_id", sa.String(length=160), nullable=True),
        sa.Column("external_url", sa.String(length=500), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["external_platform_id"], ["external_platforms.id"]),
    )
    op.create_index("ix_platform_entity_mappings_tenant_id", "platform_entity_mappings", ["tenant_id"])
    op.create_table(
        "platform_requirement_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("external_platform_id", sa.Integer(), nullable=False),
        sa.Column("local_document_type_id", sa.Integer(), nullable=False),
        sa.Column("external_requirement_id", sa.String(length=160), nullable=True),
        sa.Column("external_requirement_name", sa.String(length=240), nullable=False),
        sa.Column("direction", sa.String(length=40), nullable=False, server_default="both"),
        sa.Column("review_status", sa.String(length=60), nullable=False, server_default="pending_review"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["external_platform_id"], ["external_platforms.id"]),
        sa.ForeignKeyConstraint(["local_document_type_id"], ["document_types.id"]),
    )
    op.create_index(
        "ix_platform_requirement_mappings_tenant_id",
        "platform_requirement_mappings",
        ["tenant_id"],
    )
    op.create_table(
        "transfer_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("platform_account_id", sa.Integer(), nullable=True),
        sa.Column("external_platform_id", sa.Integer(), nullable=True),
        sa.Column("connector_key", sa.String(length=80), nullable=False),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["platform_account_id"], ["platform_accounts.id"]),
        sa.ForeignKeyConstraint(["external_platform_id"], ["external_platforms.id"]),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_transfer_jobs_tenant_id", "transfer_jobs", ["tenant_id"])
    op.create_index("ix_transfer_jobs_idempotency_key", "transfer_jobs", ["idempotency_key"])
    op.create_table(
        "transfer_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transfer_job_id", sa.Integer(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("request_metadata", sa.JSON(), nullable=False),
        sa.Column("response_metadata", sa.JSON(), nullable=False),
        sa.Column("evidence_storage_key", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["transfer_job_id"], ["transfer_jobs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_transfer_attempts_transfer_job_id", "transfer_attempts", ["transfer_job_id"])
    op.create_table(
        "external_document_statuses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("external_platform_id", sa.Integer(), nullable=False),
        sa.Column("document_version_id", sa.Integer(), nullable=False),
        sa.Column("external_document_id", sa.String(length=160), nullable=True),
        sa.Column("external_requirement_id", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("external_comment", sa.Text(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["external_platform_id"], ["external_platforms.id"]),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_external_document_statuses_tenant_id", "external_document_statuses", ["tenant_id"])
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=80), nullable=True),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("correlation_id", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"])
    op.create_index("ix_audit_logs_correlation_id", "audit_logs", ["correlation_id"])


def downgrade() -> None:
    for table, indexes in [
        ("audit_logs", ["ix_audit_logs_correlation_id", "ix_audit_logs_tenant_id"]),
        ("external_document_statuses", ["ix_external_document_statuses_tenant_id"]),
        ("transfer_attempts", ["ix_transfer_attempts_transfer_job_id"]),
        ("transfer_jobs", ["ix_transfer_jobs_idempotency_key", "ix_transfer_jobs_tenant_id"]),
        ("platform_requirement_mappings", ["ix_platform_requirement_mappings_tenant_id"]),
        ("platform_entity_mappings", ["ix_platform_entity_mappings_tenant_id"]),
        ("platform_accounts", ["ix_platform_accounts_tenant_id"]),
        ("platform_connection_methods", ["ix_platform_connection_methods_connector_key"]),
        ("document_requirements", ["ix_document_requirements_profile_id"]),
        ("requirement_profiles", ["ix_requirement_profiles_tenant_id"]),
        ("validations", []),
        ("document_versions", [
            "ix_document_versions_expires_at",
            "ix_document_versions_sha256",
            "ix_document_versions_document_id",
        ]),
        ("documents", ["ix_documents_tenant_id"]),
        ("assets", ["ix_assets_tenant_id"]),
        ("workers", ["ix_workers_tenant_id"]),
        ("projects", ["ix_projects_tenant_id"]),
        ("work_centers", ["ix_work_centers_tenant_id"]),
        ("document_types", ["ix_document_types_tenant_id"]),
        ("companies", ["ix_companies_tenant_id"]),
    ]:
        for index in indexes:
            op.drop_index(index, table_name=table)
        op.drop_table(table)
    op.drop_table("users")
    op.drop_table("roles")
    op.drop_table("external_platforms")
    op.drop_table("tenants")
