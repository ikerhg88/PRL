"""document platform expiry

Revision ID: 0010_document_platform_expiry
Revises: 0009_auth_login_signup_email_verification
Create Date: 2026-05-17
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_document_platform_expiry"
down_revision: Union[str, None] = "0009_auth_login_signup_email_verification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("document_versions", sa.Column("platform_expires_at", sa.Date(), nullable=True))
    op.add_column(
        "document_versions",
        sa.Column("expiry_review_status", sa.String(length=40), nullable=False, server_default="ok"),
    )
    op.add_column("document_versions", sa.Column("platform_expiry_source", sa.String(length=160), nullable=True))
    op.create_index("ix_document_versions_platform_expires_at", "document_versions", ["platform_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_document_versions_platform_expires_at", table_name="document_versions")
    op.drop_column("document_versions", "platform_expiry_source")
    op.drop_column("document_versions", "expiry_review_status")
    op.drop_column("document_versions", "platform_expires_at")
