"""Enforce worker uniqueness by normalized identifier hash.

Revision ID: 0015_worker_identifier_unique
Revises: 0014_platform_review_runs
Create Date: 2026-05-21 11:55:00.000000
"""

from __future__ import annotations

from alembic import op

revision = "0015_worker_identifier_unique"
down_revision = "0014_platform_review_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_workers_tenant_company_identifier_hash",
        "workers",
        ["tenant_id", "company_id", "identifier_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_workers_tenant_company_identifier_hash", table_name="workers")
