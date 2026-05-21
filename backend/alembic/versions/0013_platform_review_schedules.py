"""platform review schedules

Revision ID: 0013_platform_review_schedules
Revises: 0012_platform_rpa_contracts
Create Date: 2026-05-18
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013_platform_review_schedules"
down_revision: Union[str, None] = "0012_platform_rpa_contracts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_review_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("manifest_id", sa.Integer(), nullable=False),
        sa.Column("external_platform_id", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("interval_minutes", sa.Integer(), nullable=False, server_default="1440"),
        sa.Column("review_scope", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=60), nullable=False, server_default="disabled"),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("manual_approval_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_result_status", sa.String(length=80), nullable=True),
        sa.Column("last_result_summary", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["external_platform_id"], ["external_platforms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["manifest_id"], ["platform_rpa_manifests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "manifest_id", name="uq_platform_review_schedule_tenant_manifest"),
    )
    op.create_index("ix_platform_review_schedules_external_platform_id", "platform_review_schedules", ["external_platform_id"])
    op.create_index("ix_platform_review_schedules_manifest_id", "platform_review_schedules", ["manifest_id"])
    op.create_index("ix_platform_review_schedules_next_run_at", "platform_review_schedules", ["next_run_at"])
    op.create_index("ix_platform_review_schedules_status", "platform_review_schedules", ["status"])
    op.create_index("ix_platform_review_schedules_tenant_id", "platform_review_schedules", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_platform_review_schedules_tenant_id", table_name="platform_review_schedules")
    op.drop_index("ix_platform_review_schedules_status", table_name="platform_review_schedules")
    op.drop_index("ix_platform_review_schedules_next_run_at", table_name="platform_review_schedules")
    op.drop_index("ix_platform_review_schedules_manifest_id", table_name="platform_review_schedules")
    op.drop_index("ix_platform_review_schedules_external_platform_id", table_name="platform_review_schedules")
    op.drop_table("platform_review_schedules")
