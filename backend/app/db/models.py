from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    tax_id: Mapped[str | None] = mapped_column(String(40), unique=True)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class SaaSPlan(Base):
    __tablename__ = "saas_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    max_tenants: Mapped[int | None] = mapped_column(Integer)
    max_companies: Mapped[int | None] = mapped_column(Integer)
    max_users: Mapped[int | None] = mapped_column(Integer)
    features: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Reseller(Base):
    __tablename__ = "resellers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    tax_id: Mapped[str | None] = mapped_column(String(40), unique=True)
    contact_email: Mapped[str | None] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TenantCommercialProfile(Base):
    __tablename__ = "tenant_commercial_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), unique=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("saas_plans.id", ondelete="SET NULL"))
    reseller_id: Mapped[int | None] = mapped_column(ForeignKey("resellers.id", ondelete="SET NULL"))
    billing_mode: Mapped[str] = mapped_column(String(40), default="direct", nullable=False)
    seats_purchased: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="trial", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    email: Mapped[str] = mapped_column(String(240), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(512))
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id", ondelete="SET NULL"))
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_email_verification_tokens_hash"),
        Index("ix_email_verification_tokens_tenant_user", "tenant_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(String(80), default="signup_email_verification", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IdentityProvider(Base):
    __tablename__ = "identity_providers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider_key", name="uq_identity_providers_tenant_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    provider_key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(40), default="oidc", nullable=False)
    issuer: Mapped[str] = mapped_column(String(240), nullable=False)
    discovery_url: Mapped[str] = mapped_column(String(500), nullable=False)
    authorization_endpoint: Mapped[str] = mapped_column(String(500), nullable=False)
    token_endpoint: Mapped[str] = mapped_column(String(500), nullable=False)
    jwks_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    userinfo_endpoint: Mapped[str | None] = mapped_column(String(500))
    client_id: Mapped[str | None] = mapped_column(String(320))
    encrypted_client_secret_ref: Mapped[str | None] = mapped_column(String(240))
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    allowed_domains: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    auto_provision: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="disabled", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class UserIdentity(Base):
    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint("identity_provider_id", "subject", name="uq_user_identities_provider_subject"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    identity_provider_id: Mapped[int] = mapped_column(
        ForeignKey("identity_providers.id", ondelete="CASCADE"),
        index=True,
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(240))
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hosted_domain: Mapped[str | None] = mapped_column(String(180))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SsoAuthorizationState(Base):
    __tablename__ = "sso_authorization_states"
    __table_args__ = (UniqueConstraint("state", name="uq_sso_authorization_states_state"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    identity_provider_id: Mapped[int] = mapped_column(
        ForeignKey("identity_providers.id", ondelete="CASCADE"),
        index=True,
    )
    state: Mapped[str] = mapped_column(String(180), nullable=False)
    nonce: Mapped[str] = mapped_column(String(180), nullable=False)
    code_verifier: Mapped[str] = mapped_column(String(180), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    next_url: Mapped[str | None] = mapped_column(String(500))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OauthSignupState(Base):
    __tablename__ = "oauth_signup_states"
    __table_args__ = (UniqueConstraint("state", name="uq_oauth_signup_states_state"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(255), nullable=False)
    nonce: Mapped[str] = mapped_column(String(255), nullable=False)
    code_verifier: Mapped[str] = mapped_column(String(255), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    next_url: Mapped[str | None] = mapped_column(String(500))
    tenant_name: Mapped[str | None] = mapped_column(String(255))
    tenant_tax_id: Mapped[str | None] = mapped_column(String(80))
    company_name: Mapped[str | None] = mapped_column(String(255))
    company_tax_id: Mapped[str | None] = mapped_column(String(80))
    company_address: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("tenant_id", "tax_id", name="uq_companies_tenant_tax_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    tax_id: Mapped[str | None] = mapped_column(String(40))
    company_type: Mapped[str] = mapped_column(String(40), default="contractor", nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class UserCompanyAccess(Base):
    __tablename__ = "user_company_access"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "company_id", name="uq_user_company_access"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    access_level: Mapped[str] = mapped_column(String(40), default="viewer", nullable=False)
    role_name: Mapped[str | None] = mapped_column(String(80))
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class UserPermissionGrant(Base):
    __tablename__ = "user_permission_grants"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    scope_id: Mapped[int | None] = mapped_column(Integer, index=True)
    permission: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    effect: Mapped[str] = mapped_column(String(20), default="allow", nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class WorkCenter(Base):
    __tablename__ = "work_centers"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    risk_profile_id: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    client_company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    work_center_id: Mapped[int | None] = mapped_column(ForeignKey("work_centers.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    activity_code: Mapped[str | None] = mapped_column(String(80))
    starts_at: Mapped[date | None] = mapped_column(Date)
    ends_at: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Worker(Base):
    __tablename__ = "workers"
    __table_args__ = (
        Index(
            "uq_workers_tenant_company_identifier_hash",
            "tenant_id",
            "company_id",
            "identifier_hash",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(160), nullable=False)
    identifier_type: Mapped[str | None] = mapped_column(String(40))
    identifier_value: Mapped[str | None] = mapped_column(String(80))
    identifier_hash: Mapped[str | None] = mapped_column(String(128))
    identifier_last4: Mapped[str | None] = mapped_column(String(4))
    identifier_expires_at: Mapped[date | None] = mapped_column(Date)
    nationality: Mapped[str | None] = mapped_column(String(80))
    email: Mapped[str | None] = mapped_column(String(240))
    phone: Mapped[str | None] = mapped_column(String(60))
    social_security_number: Mapped[str | None] = mapped_column(String(40))
    social_security_last4: Mapped[str | None] = mapped_column(String(4))
    contract_type: Mapped[str | None] = mapped_column(String(80))
    starts_at: Mapped[date | None] = mapped_column(Date)
    ends_at: Mapped[date | None] = mapped_column(Date)
    work_position: Mapped[str | None] = mapped_column(String(160))
    work_center_name: Mapped[str | None] = mapped_column(String(180))
    risk_profile: Mapped[str | None] = mapped_column(String(80))
    employment_status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    medical_fitness_status: Mapped[str | None] = mapped_column(String(60))
    medical_fitness_issued_at: Mapped[date | None] = mapped_column(Date)
    medical_fitness_expires_at: Mapped[date | None] = mapped_column(Date)
    medical_fitness_provider: Mapped[str | None] = mapped_column(String(180))
    medical_fitness_restrictions: Mapped[str | None] = mapped_column(Text)
    cae_notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class WorkerTraining(Base):
    __tablename__ = "worker_trainings"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("workers.id", ondelete="CASCADE"), index=True)
    course_code: Mapped[str | None] = mapped_column(String(100))
    course_name: Mapped[str] = mapped_column(String(180), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(180))
    hours: Mapped[int | None] = mapped_column(Integer)
    issued_at: Mapped[date | None] = mapped_column(Date)
    expires_at: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(60), default="valid_internal", nullable=False)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class WorkerWorkAssignment(Base):
    __tablename__ = "worker_work_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("workers.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    work_center_id: Mapped[int | None] = mapped_column(ForeignKey("work_centers.id", ondelete="SET NULL"))
    work_name: Mapped[str] = mapped_column(String(180), nullable=False)
    client_company_name: Mapped[str | None] = mapped_column(String(180))
    role: Mapped[str | None] = mapped_column(String(120))
    starts_at: Mapped[date | None] = mapped_column(Date)
    ends_at: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(60), default="active", nullable=False)
    source: Mapped[str] = mapped_column(String(60), default="manual", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    asset_type: Mapped[str] = mapped_column(String(40), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    serial_number: Mapped[str | None] = mapped_column(String(120))
    plate_number: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentType(Base):
    __tablename__ = "document_types"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_document_types_tenant_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    entity_scope: Mapped[str] = mapped_column(String(40), nullable=False)
    is_common_cae_type: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_expiration: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_validity_days: Mapped[int | None] = mapped_column(Integer)
    retention_days: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    document_type_id: Mapped[int] = mapped_column(ForeignKey("document_types.id"))
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    current_version_id: Mapped[int | None] = mapped_column(Integer)
    status_internal: Mapped[str] = mapped_column(String(60), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_number", name="uq_document_versions_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    file_storage_key: Mapped[str] = mapped_column(String(320), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(240), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream", nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    issued_at: Mapped[date | None] = mapped_column(Date)
    expires_at: Mapped[date | None] = mapped_column(Date, index=True)
    platform_expires_at: Mapped[date | None] = mapped_column(Date, index=True)
    expiry_review_status: Mapped[str] = mapped_column(String(40), default="ok", nullable=False)
    platform_expiry_source: Mapped[str | None] = mapped_column(String(160))
    source: Mapped[str] = mapped_column(String(40), default="manual", nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentIntake(Base):
    __tablename__ = "document_intakes"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    original_filename: Mapped[str] = mapped_column(String(240), nullable=False)
    file_storage_key: Mapped[str] = mapped_column(String(320), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(60), default="pending_review", nullable=False)
    intake_scope: Mapped[str] = mapped_column(String(40), default="auto", nullable=False)
    requested_company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    requested_worker_id: Mapped[int | None] = mapped_column(ForeignKey("workers.id", ondelete="SET NULL"))
    target_notes: Mapped[str | None] = mapped_column(Text)
    extraction_engine: Mapped[str] = mapped_column(String(160), nullable=False)
    extracted_text_excerpt: Mapped[str | None] = mapped_column(Text)
    text_confidence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    predicted_document_type_id: Mapped[int | None] = mapped_column(ForeignKey("document_types.id"))
    predicted_entity_type: Mapped[str | None] = mapped_column(String(40))
    predicted_entity_id: Mapped[int | None] = mapped_column(Integer)
    predicted_company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    predicted_worker_id: Mapped[int | None] = mapped_column(ForeignKey("workers.id", ondelete="SET NULL"))
    issued_at: Mapped[date | None] = mapped_column(Date)
    expires_at: Mapped[date | None] = mapped_column(Date)
    confidence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    classification_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    signals_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    created_version_id: Mapped[int | None] = mapped_column(ForeignKey("document_versions.id", ondelete="SET NULL"))
    review_comment: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Validation(Base):
    __tablename__ = "validations"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"))
    validator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(60), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RequirementProfile(Base):
    __tablename__ = "requirement_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    client_company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    work_center_id: Mapped[int | None] = mapped_column(ForeignKey("work_centers.id", ondelete="SET NULL"))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    activity_code: Mapped[str | None] = mapped_column(String(80))
    risk_level: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentRequirement(Base):
    __tablename__ = "document_requirements"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("requirement_profiles.id", ondelete="CASCADE"), index=True)
    document_type_id: Mapped[int] = mapped_column(ForeignKey("document_types.id"))
    entity_scope: Mapped[str] = mapped_column(String(40), nullable=False)
    mandatory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    blocks_access: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_human_validation: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expiration_warning_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    validity_rule: Mapped[str | None] = mapped_column(String(120))
    platform_id: Mapped[int | None] = mapped_column(ForeignKey("external_platforms.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExternalPlatform(Base):
    __tablename__ = "external_platforms"

    id: Mapped[int] = mapped_column(primary_key=True)
    platform_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="cataloged", nullable=False)
    is_commercial: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    connection_methods: Mapped[list[PlatformConnectionMethod]] = relationship(
        back_populates="platform",
        cascade="all, delete-orphan",
    )


class PlatformConnectionMethod(Base):
    __tablename__ = "platform_connection_methods"
    __table_args__ = (
        UniqueConstraint(
            "external_platform_id",
            "method_key",
            name="uq_platform_connection_methods_platform_method",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    external_platform_id: Mapped[int] = mapped_column(
        ForeignKey("external_platforms.id", ondelete="CASCADE"),
        nullable=False,
    )
    method_key: Mapped[str] = mapped_column(String(80), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(40), nullable=False)
    connector_key: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(60), nullable=False)
    implemented: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dry_run_supported: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    manual_approval_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    platform: Mapped[ExternalPlatform] = relationship(back_populates="connection_methods")


class PlatformAccount(Base):
    __tablename__ = "platform_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    external_platform_id: Mapped[int] = mapped_column(ForeignKey("external_platforms.id"))
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    auth_type: Mapped[str] = mapped_column(String(60), default="manual", nullable=False)
    encrypted_secret_ref: Mapped[str | None] = mapped_column(String(240))
    mode: Mapped[str] = mapped_column(String(40), default="disabled", nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    manual_approval_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkerPlatformRegistration(Base):
    __tablename__ = "worker_platform_registrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("workers.id", ondelete="CASCADE"), index=True)
    platform_account_id: Mapped[int | None] = mapped_column(ForeignKey("platform_accounts.id", ondelete="SET NULL"))
    external_platform_id: Mapped[int | None] = mapped_column(ForeignKey("external_platforms.id", ondelete="SET NULL"))
    platform_name: Mapped[str] = mapped_column(String(180), nullable=False)
    external_worker_id: Mapped[str | None] = mapped_column(String(180))
    registration_status: Mapped[str] = mapped_column(String(60), default="not_synced", nullable=False)
    assignment_scope: Mapped[str | None] = mapped_column(String(180))
    source: Mapped[str] = mapped_column(String(60), default="manual", nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class PlatformAccountUserAccess(Base):
    __tablename__ = "platform_account_user_access"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "platform_account_id",
            "user_id",
            name="uq_platform_account_user_access",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    platform_account_id: Mapped[int] = mapped_column(
        ForeignKey("platform_accounts.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    access_level: Mapped[str] = mapped_column(String(40), default="viewer", nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    allowed_operations: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class PlatformEntityMapping(Base):
    __tablename__ = "platform_entity_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    external_platform_id: Mapped[int] = mapped_column(ForeignKey("external_platforms.id"))
    local_entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    local_entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    external_entity_id: Mapped[str | None] = mapped_column(String(160))
    external_url: Mapped[str | None] = mapped_column(String(500))
    confidence: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlatformRequirementMapping(Base):
    __tablename__ = "platform_requirement_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    external_platform_id: Mapped[int] = mapped_column(ForeignKey("external_platforms.id"))
    local_document_type_id: Mapped[int] = mapped_column(ForeignKey("document_types.id"))
    external_requirement_id: Mapped[str | None] = mapped_column(String(160))
    external_requirement_name: Mapped[str] = mapped_column(String(240), nullable=False)
    direction: Mapped[str] = mapped_column(String(40), default="both", nullable=False)
    review_status: Mapped[str] = mapped_column(String(60), default="pending_review", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlatformStructureSnapshot(Base):
    __tablename__ = "platform_structure_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    external_platform_id: Mapped[int | None] = mapped_column(ForeignKey("external_platforms.id", ondelete="SET NULL"), index=True)
    platform_account_id: Mapped[int | None] = mapped_column(ForeignKey("platform_accounts.id", ondelete="SET NULL"), index=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"), index=True)
    platform_label: Mapped[str] = mapped_column(String(180), nullable=False)
    host: Mapped[str | None] = mapped_column(String(240), index=True)
    login_status: Mapped[str | None] = mapped_column(String(80), index=True)
    source_type: Mapped[str] = mapped_column(String(60), default="readonly_capture", nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(60), default="mapped", nullable=False)
    structure_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class PlatformDiscoveredLabel(Base):
    __tablename__ = "platform_discovered_labels"
    __table_args__ = (
        Index("ix_platform_discovered_labels_tenant_standard", "tenant_id", "standard_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("platform_structure_snapshots.id", ondelete="CASCADE"), index=True)
    external_platform_id: Mapped[int | None] = mapped_column(ForeignKey("external_platforms.id", ondelete="SET NULL"), index=True)
    platform_account_id: Mapped[int | None] = mapped_column(ForeignKey("platform_accounts.id", ondelete="SET NULL"), index=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"), index=True)
    label_kind: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    raw_label: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_label: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    page_label: Mapped[str | None] = mapped_column(String(180))
    entity_scope: Mapped[str | None] = mapped_column(String(60), index=True)
    standard_key: Mapped[str | None] = mapped_column(String(120), index=True)
    confidence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    review_status: Mapped[str] = mapped_column(String(60), default="proposed", nullable=False, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class PlatformRpaManifest(Base):
    __tablename__ = "platform_rpa_manifests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "platform_slug", name="uq_platform_rpa_manifest_tenant_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    external_platform_id: Mapped[int | None] = mapped_column(ForeignKey("external_platforms.id", ondelete="SET NULL"), index=True)
    platform_slug: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    platform_name: Mapped[str] = mapped_column(String(180), nullable=False)
    family: Mapped[str | None] = mapped_column(String(120))
    mode: Mapped[str] = mapped_column(String(80), default="authorized_rpa", nullable=False)
    status: Mapped[str] = mapped_column(String(80), default="proposal_disabled", nullable=False, index=True)
    priority_group: Mapped[str | None] = mapped_column(String(80), index=True)
    source_ref: Mapped[str | None] = mapped_column(String(500))
    schema_version: Mapped[str | None] = mapped_column(String(40))
    generated_at: Mapped[str | None] = mapped_column(String(40))
    hosts: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    entry_urls: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    allowed_operations: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    allowed_entity_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    requires_signed_authorization: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    dry_run_default: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    manual_approval_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    rpa_assisted_on_control: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sensitive_data_minimization_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auxiliary_platform_review_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    manifest_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class PlatformRpaAccountProposal(Base):
    __tablename__ = "platform_rpa_account_proposals"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_platform_account_id",
            name="uq_platform_rpa_account_tenant_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    manifest_id: Mapped[int] = mapped_column(ForeignKey("platform_rpa_manifests.id", ondelete="CASCADE"), index=True)
    external_platform_id: Mapped[int | None] = mapped_column(ForeignKey("external_platforms.id", ondelete="SET NULL"), index=True)
    platform_account_id: Mapped[int | None] = mapped_column(ForeignKey("platform_accounts.id", ondelete="SET NULL"), index=True)
    source_platform_account_id: Mapped[str] = mapped_column(String(180), nullable=False)
    company_source_label: Mapped[str | None] = mapped_column(String(80), index=True)
    source_excel_sheet: Mapped[str | None] = mapped_column(String(80))
    source_excel_row: Mapped[int | None] = mapped_column(Integer)
    external_company_name: Mapped[str | None] = mapped_column(String(240))
    entry_url: Mapped[str | None] = mapped_column(String(500))
    host: Mapped[str | None] = mapped_column(String(240), index=True)
    user_hint_masked: Mapped[str | None] = mapped_column(String(180))
    credential_secret_ref: Mapped[str | None] = mapped_column(String(320))
    account_status: Mapped[str] = mapped_column(String(80), default="active_in_source", nullable=False)
    status: Mapped[str] = mapped_column(String(80), default="proposal_disabled", nullable=False, index=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    manual_approval_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allowed_operations: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    allowed_entity_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class PlatformRpaMappingProposal(Base):
    __tablename__ = "platform_rpa_mapping_proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    manifest_id: Mapped[int] = mapped_column(ForeignKey("platform_rpa_manifests.id", ondelete="CASCADE"), index=True)
    external_platform_id: Mapped[int | None] = mapped_column(ForeignKey("external_platforms.id", ondelete="SET NULL"), index=True)
    mapping_kind: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_scope: Mapped[str | None] = mapped_column(String(60), index=True)
    iker_key: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    external_label: Mapped[str | None] = mapped_column(String(300))
    external_catalog_value: Mapped[str | None] = mapped_column(String(240))
    requirement: Mapped[str | None] = mapped_column(String(120))
    applies_to: Mapped[str | None] = mapped_column(String(160))
    review_status: Mapped[str] = mapped_column(String(80), default="pending_review", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(80), default="proposed_pending_platform_validation", nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class PlatformReviewSchedule(Base):
    __tablename__ = "platform_review_schedules"
    __table_args__ = (
        UniqueConstraint("tenant_id", "manifest_id", name="uq_platform_review_schedule_tenant_manifest"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    manifest_id: Mapped[int] = mapped_column(ForeignKey("platform_rpa_manifests.id", ondelete="CASCADE"), index=True)
    external_platform_id: Mapped[int | None] = mapped_column(ForeignKey("external_platforms.id", ondelete="SET NULL"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=1440, nullable=False)
    review_scope: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(60), default="disabled", nullable=False, index=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    manual_approval_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_result_status: Mapped[str | None] = mapped_column(String(80))
    last_result_summary: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class PlatformReviewRun(Base):
    __tablename__ = "platform_review_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("platform_review_schedules.id", ondelete="CASCADE"), index=True)
    manifest_id: Mapped[int] = mapped_column(ForeignKey("platform_rpa_manifests.id", ondelete="CASCADE"), index=True)
    account_proposal_id: Mapped[int | None] = mapped_column(ForeignKey("platform_rpa_account_proposals.id", ondelete="SET NULL"), index=True)
    external_platform_id: Mapped[int | None] = mapped_column(ForeignKey("external_platforms.id", ondelete="SET NULL"), index=True)
    platform_slug: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    platform_name: Mapped[str] = mapped_column(String(180), nullable=False)
    operation: Mapped[str] = mapped_column(String(80), default="read_external_status", nullable=False)
    trigger_source: Mapped[str] = mapped_column(String(60), default="manual_run_now", nullable=False)
    status: Mapped[str] = mapped_column(String(80), default="created", nullable=False, index=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    manual_approval_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_status: Mapped[str | None] = mapped_column(String(80))
    result_summary: Mapped[str | None] = mapped_column(Text)
    error_summary: Mapped[str | None] = mapped_column(Text)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TransferJob(Base):
    __tablename__ = "transfer_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    platform_account_id: Mapped[int | None] = mapped_column(ForeignKey("platform_accounts.id"))
    external_platform_id: Mapped[int | None] = mapped_column(ForeignKey("external_platforms.id"))
    connector_key: Mapped[str] = mapped_column(String(80), nullable=False)
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str | None] = mapped_column(String(500), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TransferAttempt(Base):
    __tablename__ = "transfer_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_job_id: Mapped[int] = mapped_column(ForeignKey("transfer_jobs.id", ondelete="CASCADE"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    request_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    response_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evidence_storage_key: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExternalDocumentStatus(Base):
    __tablename__ = "external_document_statuses"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    external_platform_id: Mapped[int] = mapped_column(ForeignKey("external_platforms.id"))
    document_version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"))
    external_document_id: Mapped[str | None] = mapped_column(String(160))
    external_requirement_id: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    external_comment: Mapped[str | None] = mapped_column(Text)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id", ondelete="SET NULL"), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(80))
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    correlation_id: Mapped[str | None] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
