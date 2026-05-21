"""document intake ocr

Revision ID: 0004_document_intake_ocr
Revises: 0003_google_sso_identity
Create Date: 2026-05-16
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_document_intake_ocr"
down_revision: Union[str, None] = "0003_google_sso_identity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_intakes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), nullable=True),
        sa.Column("original_filename", sa.String(length=240), nullable=False),
        sa.Column("file_storage_key", sa.String(length=320), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=60), nullable=False, server_default="pending_review"),
        sa.Column("extraction_engine", sa.String(length=160), nullable=False),
        sa.Column("extracted_text_excerpt", sa.Text(), nullable=True),
        sa.Column("text_confidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("predicted_document_type_id", sa.Integer(), nullable=True),
        sa.Column("predicted_entity_type", sa.String(length=40), nullable=True),
        sa.Column("predicted_entity_id", sa.Integer(), nullable=True),
        sa.Column("predicted_company_id", sa.Integer(), nullable=True),
        sa.Column("predicted_worker_id", sa.Integer(), nullable=True),
        sa.Column("issued_at", sa.Date(), nullable=True),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("classification_json", sa.JSON(), nullable=False),
        sa.Column("signals_json", sa.JSON(), nullable=False),
        sa.Column("created_document_id", sa.Integer(), nullable=True),
        sa.Column("created_version_id", sa.Integer(), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["predicted_document_type_id"], ["document_types.id"]),
        sa.ForeignKeyConstraint(["predicted_company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["predicted_worker_id"], ["workers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_version_id"], ["document_versions.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_document_intakes_tenant_id", "document_intakes", ["tenant_id"])
    op.create_index("ix_document_intakes_sha256", "document_intakes", ["sha256"])


def downgrade() -> None:
    op.drop_index("ix_document_intakes_sha256", table_name="document_intakes")
    op.drop_index("ix_document_intakes_tenant_id", table_name="document_intakes")
    op.drop_table("document_intakes")
