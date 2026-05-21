"""auth login signup email verification

Revision ID: 0009_auth_login_signup_email_verification
Revises: 0008_worker_imports_assignments_platforms
Create Date: 2026-05-17
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_auth_login_signup_email_verification"
down_revision: Union[str, None] = "0008_worker_imports_assignments_platforms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=80), nullable=False, server_default="signup_email_verification"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash", name="uq_email_verification_tokens_hash"),
    )
    op.create_index("ix_email_verification_tokens_tenant_id", "email_verification_tokens", ["tenant_id"])
    op.create_index("ix_email_verification_tokens_user_id", "email_verification_tokens", ["user_id"])
    op.create_index(
        "ix_email_verification_tokens_tenant_user",
        "email_verification_tokens",
        ["tenant_id", "user_id"],
    )

    op.create_table(
        "oauth_signup_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("state", sa.String(length=255), nullable=False),
        sa.Column("nonce", sa.String(length=255), nullable=False),
        sa.Column("code_verifier", sa.String(length=255), nullable=False),
        sa.Column("redirect_uri", sa.String(length=500), nullable=False),
        sa.Column("next_url", sa.String(length=500), nullable=True),
        sa.Column("tenant_name", sa.String(length=255), nullable=True),
        sa.Column("tenant_tax_id", sa.String(length=80), nullable=True),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("company_tax_id", sa.String(length=80), nullable=True),
        sa.Column("company_address", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("state", name="uq_oauth_signup_states_state"),
    )


def downgrade() -> None:
    op.drop_table("oauth_signup_states")
    op.drop_index("ix_email_verification_tokens_tenant_user", table_name="email_verification_tokens")
    op.drop_index("ix_email_verification_tokens_user_id", table_name="email_verification_tokens")
    op.drop_index("ix_email_verification_tokens_tenant_id", table_name="email_verification_tokens")
    op.drop_table("email_verification_tokens")

    op.drop_column("users", "last_login_at")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "password_hash")
