"""worker imports assignments and platform registrations

Revision ID: 0008_worker_imports_assignments_platforms
Revises: 0007_worker_cae_and_intake_scope
Create Date: 2026-05-16
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_worker_imports_assignments_platforms"
down_revision: Union[str, None] = "0007_worker_cae_and_intake_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workers", sa.Column("identifier_value", sa.String(length=80), nullable=True))
    op.add_column("workers", sa.Column("social_security_number", sa.String(length=40), nullable=True))
    op.create_index("ix_workers_identifier_value", "workers", ["identifier_value"])

    op.create_table(
        "worker_work_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("work_center_id", sa.Integer(), nullable=True),
        sa.Column("work_name", sa.String(length=180), nullable=False),
        sa.Column("client_company_name", sa.String(length=180), nullable=True),
        sa.Column("role", sa.String(length=120), nullable=True),
        sa.Column("starts_at", sa.Date(), nullable=True),
        sa.Column("ends_at", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=60), nullable=False, server_default="active"),
        sa.Column("source", sa.String(length=60), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["work_center_id"], ["work_centers.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_worker_work_assignments_tenant_id", "worker_work_assignments", ["tenant_id"])
    op.create_index("ix_worker_work_assignments_worker_id", "worker_work_assignments", ["worker_id"])

    op.create_table(
        "worker_platform_registrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.Integer(), nullable=False),
        sa.Column("platform_account_id", sa.Integer(), nullable=True),
        sa.Column("external_platform_id", sa.Integer(), nullable=True),
        sa.Column("platform_name", sa.String(length=180), nullable=False),
        sa.Column("external_worker_id", sa.String(length=180), nullable=True),
        sa.Column("registration_status", sa.String(length=60), nullable=False, server_default="not_synced"),
        sa.Column("assignment_scope", sa.String(length=180), nullable=True),
        sa.Column("source", sa.String(length=60), nullable=False, server_default="manual"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["platform_account_id"], ["platform_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["external_platform_id"], ["external_platforms.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_worker_platform_registrations_tenant_id", "worker_platform_registrations", ["tenant_id"])
    op.create_index("ix_worker_platform_registrations_worker_id", "worker_platform_registrations", ["worker_id"])


def downgrade() -> None:
    op.drop_index("ix_worker_platform_registrations_worker_id", table_name="worker_platform_registrations")
    op.drop_index("ix_worker_platform_registrations_tenant_id", table_name="worker_platform_registrations")
    op.drop_table("worker_platform_registrations")

    op.drop_index("ix_worker_work_assignments_worker_id", table_name="worker_work_assignments")
    op.drop_index("ix_worker_work_assignments_tenant_id", table_name="worker_work_assignments")
    op.drop_table("worker_work_assignments")

    op.drop_index("ix_workers_identifier_value", table_name="workers")
    op.drop_column("workers", "social_security_number")
    op.drop_column("workers", "identifier_value")
