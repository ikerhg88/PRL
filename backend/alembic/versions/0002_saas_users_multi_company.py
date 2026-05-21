"""saas users multi company

Revision ID: 0002_saas_users_multi_company
Revises: 0001_initial_platform_catalog
Create Date: 2026-05-16
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_saas_users_multi_company"
down_revision: Union[str, None] = "0001_initial_platform_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "saas_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("max_tenants", sa.Integer(), nullable=True),
        sa.Column("max_companies", sa.Integer(), nullable=True),
        sa.Column("max_users", sa.Integer(), nullable=True),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("plan_key", name="uq_saas_plans_plan_key"),
    )
    op.create_table(
        "resellers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("tax_id", sa.String(length=40), nullable=True),
        sa.Column("contact_email", sa.String(length=240), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tax_id", name="uq_resellers_tax_id"),
    )
    op.create_table(
        "tenant_commercial_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=True),
        sa.Column("reseller_id", sa.Integer(), nullable=True),
        sa.Column("billing_mode", sa.String(length=40), nullable=False, server_default="direct"),
        sa.Column("seats_purchased", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="trial"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["saas_plans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reseller_id"], ["resellers.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_commercial_profiles_tenant_id"),
    )
    op.create_table(
        "user_company_access",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("access_level", sa.String(length=40), nullable=False, server_default="viewer"),
        sa.Column("role_name", sa.String(length=80), nullable=True),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "user_id", "company_id", name="uq_user_company_access"),
    )
    op.create_index("ix_user_company_access_tenant_id", "user_company_access", ["tenant_id"])
    op.create_index("ix_user_company_access_user_id", "user_company_access", ["user_id"])
    op.create_index("ix_user_company_access_company_id", "user_company_access", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_user_company_access_company_id", table_name="user_company_access")
    op.drop_index("ix_user_company_access_user_id", table_name="user_company_access")
    op.drop_index("ix_user_company_access_tenant_id", table_name="user_company_access")
    op.drop_table("user_company_access")
    op.drop_table("tenant_commercial_profiles")
    op.drop_table("resellers")
    op.drop_table("saas_plans")
