"""platform user access admin

Revision ID: 0005_platform_user_access_admin
Revises: 0004_document_intake_ocr
Create Date: 2026-05-16
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_platform_user_access_admin"
down_revision: Union[str, None] = "0004_document_intake_ocr"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_account_user_access",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("platform_account_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("access_level", sa.String(length=40), nullable=False, server_default="viewer"),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("allowed_operations", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["platform_account_id"], ["platform_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id",
            "platform_account_id",
            "user_id",
            name="uq_platform_account_user_access",
        ),
    )
    op.create_index(
        "ix_platform_account_user_access_tenant_id",
        "platform_account_user_access",
        ["tenant_id"],
    )
    op.create_index(
        "ix_platform_account_user_access_platform_account_id",
        "platform_account_user_access",
        ["platform_account_id"],
    )
    op.create_index(
        "ix_platform_account_user_access_user_id",
        "platform_account_user_access",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_platform_account_user_access_user_id", table_name="platform_account_user_access")
    op.drop_index("ix_platform_account_user_access_platform_account_id", table_name="platform_account_user_access")
    op.drop_index("ix_platform_account_user_access_tenant_id", table_name="platform_account_user_access")
    op.drop_table("platform_account_user_access")
