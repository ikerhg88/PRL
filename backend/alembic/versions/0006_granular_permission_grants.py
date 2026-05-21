"""granular permission grants

Revision ID: 0006_granular_permission_grants
Revises: 0005_platform_user_access_admin
Create Date: 2026-05-16
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_granular_permission_grants"
down_revision: Union[str, None] = "0005_platform_user_access_admin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_permission_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("scope_type", sa.String(length=40), nullable=False),
        sa.Column("scope_id", sa.Integer(), nullable=True),
        sa.Column("permission", sa.String(length=120), nullable=False),
        sa.Column("effect", sa.String(length=20), nullable=False, server_default="allow"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_user_permission_grants_tenant_id", "user_permission_grants", ["tenant_id"])
    op.create_index("ix_user_permission_grants_user_id", "user_permission_grants", ["user_id"])
    op.create_index("ix_user_permission_grants_scope_type", "user_permission_grants", ["scope_type"])
    op.create_index("ix_user_permission_grants_scope_id", "user_permission_grants", ["scope_id"])
    op.create_index("ix_user_permission_grants_permission", "user_permission_grants", ["permission"])


def downgrade() -> None:
    op.drop_index("ix_user_permission_grants_permission", table_name="user_permission_grants")
    op.drop_index("ix_user_permission_grants_scope_id", table_name="user_permission_grants")
    op.drop_index("ix_user_permission_grants_scope_type", table_name="user_permission_grants")
    op.drop_index("ix_user_permission_grants_user_id", table_name="user_permission_grants")
    op.drop_index("ix_user_permission_grants_tenant_id", table_name="user_permission_grants")
    op.drop_table("user_permission_grants")
