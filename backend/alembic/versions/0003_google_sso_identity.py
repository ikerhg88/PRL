"""google sso identity

Revision ID: 0003_google_sso_identity
Revises: 0002_saas_users_multi_company
Create Date: 2026-05-16
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_google_sso_identity"
down_revision: Union[str, None] = "0002_saas_users_multi_company"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "identity_providers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("provider_key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("provider_type", sa.String(length=40), nullable=False, server_default="oidc"),
        sa.Column("issuer", sa.String(length=240), nullable=False),
        sa.Column("discovery_url", sa.String(length=500), nullable=False),
        sa.Column("authorization_endpoint", sa.String(length=500), nullable=False),
        sa.Column("token_endpoint", sa.String(length=500), nullable=False),
        sa.Column("jwks_uri", sa.String(length=500), nullable=False),
        sa.Column("userinfo_endpoint", sa.String(length=500), nullable=True),
        sa.Column("client_id", sa.String(length=320), nullable=True),
        sa.Column("encrypted_client_secret_ref", sa.String(length=240), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("allowed_domains", sa.JSON(), nullable=False),
        sa.Column("auto_provision", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="disabled"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "provider_key", name="uq_identity_providers_tenant_key"),
    )
    op.create_index("ix_identity_providers_tenant_id", "identity_providers", ["tenant_id"])
    op.create_table(
        "user_identities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("identity_provider_id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=240), nullable=True),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("hosted_domain", sa.String(length=180), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["identity_provider_id"], ["identity_providers.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("identity_provider_id", "subject", name="uq_user_identities_provider_subject"),
    )
    op.create_index("ix_user_identities_tenant_id", "user_identities", ["tenant_id"])
    op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"])
    op.create_index("ix_user_identities_identity_provider_id", "user_identities", ["identity_provider_id"])
    op.create_table(
        "sso_authorization_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("identity_provider_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=180), nullable=False),
        sa.Column("nonce", sa.String(length=180), nullable=False),
        sa.Column("code_verifier", sa.String(length=180), nullable=False),
        sa.Column("redirect_uri", sa.String(length=500), nullable=False),
        sa.Column("next_url", sa.String(length=500), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["identity_provider_id"], ["identity_providers.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("state", name="uq_sso_authorization_states_state"),
    )
    op.create_index("ix_sso_authorization_states_tenant_id", "sso_authorization_states", ["tenant_id"])
    op.create_index(
        "ix_sso_authorization_states_identity_provider_id",
        "sso_authorization_states",
        ["identity_provider_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_sso_authorization_states_identity_provider_id", table_name="sso_authorization_states")
    op.drop_index("ix_sso_authorization_states_tenant_id", table_name="sso_authorization_states")
    op.drop_table("sso_authorization_states")
    op.drop_index("ix_user_identities_identity_provider_id", table_name="user_identities")
    op.drop_index("ix_user_identities_user_id", table_name="user_identities")
    op.drop_index("ix_user_identities_tenant_id", table_name="user_identities")
    op.drop_table("user_identities")
    op.drop_index("ix_identity_providers_tenant_id", table_name="identity_providers")
    op.drop_table("identity_providers")
