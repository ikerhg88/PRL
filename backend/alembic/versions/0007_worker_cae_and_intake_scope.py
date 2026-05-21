"""worker CAE fields and OCR intake scope

Revision ID: 0007_worker_cae_and_intake_scope
Revises: 0006_granular_permission_grants
Create Date: 2026-05-16
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_worker_cae_and_intake_scope"
down_revision: Union[str, None] = "0006_granular_permission_grants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workers", sa.Column("identifier_expires_at", sa.Date(), nullable=True))
    op.add_column("workers", sa.Column("email", sa.String(length=240), nullable=True))
    op.add_column("workers", sa.Column("phone", sa.String(length=60), nullable=True))
    op.add_column("workers", sa.Column("social_security_last4", sa.String(length=4), nullable=True))
    op.add_column("workers", sa.Column("contract_type", sa.String(length=80), nullable=True))
    op.add_column("workers", sa.Column("starts_at", sa.Date(), nullable=True))
    op.add_column("workers", sa.Column("ends_at", sa.Date(), nullable=True))
    op.add_column("workers", sa.Column("work_center_name", sa.String(length=180), nullable=True))
    op.add_column("workers", sa.Column("risk_profile", sa.String(length=80), nullable=True))
    op.add_column("workers", sa.Column("medical_fitness_issued_at", sa.Date(), nullable=True))
    op.add_column("workers", sa.Column("medical_fitness_provider", sa.String(length=180), nullable=True))
    op.add_column("workers", sa.Column("medical_fitness_restrictions", sa.Text(), nullable=True))
    op.add_column("workers", sa.Column("cae_notes", sa.Text(), nullable=True))

    op.create_table(
        "worker_trainings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.Integer(), nullable=False),
        sa.Column("course_code", sa.String(length=100), nullable=True),
        sa.Column("course_name", sa.String(length=180), nullable=False),
        sa.Column("provider", sa.String(length=180), nullable=True),
        sa.Column("hours", sa.Integer(), nullable=True),
        sa.Column("issued_at", sa.Date(), nullable=True),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=60), nullable=False, server_default="valid_internal"),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_worker_trainings_tenant_id", "worker_trainings", ["tenant_id"])
    op.create_index("ix_worker_trainings_worker_id", "worker_trainings", ["worker_id"])
    op.create_index("ix_worker_trainings_expires_at", "worker_trainings", ["expires_at"])

    op.add_column(
        "document_intakes",
        sa.Column("intake_scope", sa.String(length=40), nullable=False, server_default="auto"),
    )
    op.add_column("document_intakes", sa.Column("requested_company_id", sa.Integer(), nullable=True))
    op.add_column("document_intakes", sa.Column("requested_worker_id", sa.Integer(), nullable=True))
    op.add_column("document_intakes", sa.Column("target_notes", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_document_intakes_requested_company_id",
        "document_intakes",
        "companies",
        ["requested_company_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_document_intakes_requested_worker_id",
        "document_intakes",
        "workers",
        ["requested_worker_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_document_intakes_requested_worker_id", "document_intakes", type_="foreignkey")
    op.drop_constraint("fk_document_intakes_requested_company_id", "document_intakes", type_="foreignkey")
    op.drop_column("document_intakes", "target_notes")
    op.drop_column("document_intakes", "requested_worker_id")
    op.drop_column("document_intakes", "requested_company_id")
    op.drop_column("document_intakes", "intake_scope")

    op.drop_index("ix_worker_trainings_expires_at", table_name="worker_trainings")
    op.drop_index("ix_worker_trainings_worker_id", table_name="worker_trainings")
    op.drop_index("ix_worker_trainings_tenant_id", table_name="worker_trainings")
    op.drop_table("worker_trainings")

    op.drop_column("workers", "cae_notes")
    op.drop_column("workers", "medical_fitness_restrictions")
    op.drop_column("workers", "medical_fitness_provider")
    op.drop_column("workers", "medical_fitness_issued_at")
    op.drop_column("workers", "risk_profile")
    op.drop_column("workers", "work_center_name")
    op.drop_column("workers", "ends_at")
    op.drop_column("workers", "starts_at")
    op.drop_column("workers", "contract_type")
    op.drop_column("workers", "social_security_last4")
    op.drop_column("workers", "phone")
    op.drop_column("workers", "email")
    op.drop_column("workers", "identifier_expires_at")
