"""platform review runs

Revision ID: 0014_platform_review_runs
Revises: 0013_platform_review_schedules
Create Date: 2026-05-18
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0014_platform_review_runs"
down_revision: Union[str, None] = "0013_platform_review_schedules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_review_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("schedule_id", sa.Integer(), nullable=False),
        sa.Column("manifest_id", sa.Integer(), nullable=False),
        sa.Column("account_proposal_id", sa.Integer(), nullable=True),
        sa.Column("external_platform_id", sa.Integer(), nullable=True),
        sa.Column("platform_slug", sa.String(length=120), nullable=False),
        sa.Column("platform_name", sa.String(length=180), nullable=False),
        sa.Column("operation", sa.String(length=80), nullable=False, server_default="read_external_status"),
        sa.Column("trigger_source", sa.String(length=60), nullable=False, server_default="manual_run_now"),
        sa.Column("status", sa.String(length=80), nullable=False, server_default="created"),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("manual_approval_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_status", sa.String(length=80), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["account_proposal_id"], ["platform_rpa_account_proposals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["external_platform_id"], ["external_platforms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["manifest_id"], ["platform_rpa_manifests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["schedule_id"], ["platform_review_schedules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platform_review_runs_account_proposal_id", "platform_review_runs", ["account_proposal_id"])
    op.create_index("ix_platform_review_runs_external_platform_id", "platform_review_runs", ["external_platform_id"])
    op.create_index("ix_platform_review_runs_manifest_id", "platform_review_runs", ["manifest_id"])
    op.create_index("ix_platform_review_runs_platform_slug", "platform_review_runs", ["platform_slug"])
    op.create_index("ix_platform_review_runs_schedule_id", "platform_review_runs", ["schedule_id"])
    op.create_index("ix_platform_review_runs_status", "platform_review_runs", ["status"])
    op.create_index("ix_platform_review_runs_tenant_id", "platform_review_runs", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_platform_review_runs_tenant_id", table_name="platform_review_runs")
    op.drop_index("ix_platform_review_runs_status", table_name="platform_review_runs")
    op.drop_index("ix_platform_review_runs_schedule_id", table_name="platform_review_runs")
    op.drop_index("ix_platform_review_runs_platform_slug", table_name="platform_review_runs")
    op.drop_index("ix_platform_review_runs_manifest_id", table_name="platform_review_runs")
    op.drop_index("ix_platform_review_runs_external_platform_id", table_name="platform_review_runs")
    op.drop_index("ix_platform_review_runs_account_proposal_id", table_name="platform_review_runs")
    op.drop_table("platform_review_runs")
