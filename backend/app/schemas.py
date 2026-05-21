from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TenantCreate(BaseModel):
    name: str
    tax_id: str | None = None


class TenantRead(ApiModel):
    id: int
    name: str
    tax_id: str | None
    status: str
    created_at: datetime | None = None


class SaaSPlanCreate(BaseModel):
    plan_key: str
    name: str
    max_tenants: int | None = None
    max_companies: int | None = None
    max_users: int | None = None
    features: list[str] = Field(default_factory=list)
    status: str = "active"


class SaaSPlanRead(ApiModel):
    id: int
    plan_key: str
    name: str
    max_tenants: int | None
    max_companies: int | None
    max_users: int | None
    features: list[str]
    status: str


class ResellerCreate(BaseModel):
    name: str
    tax_id: str | None = None
    contact_email: str | None = None
    status: str = "active"


class ResellerRead(ApiModel):
    id: int
    name: str
    tax_id: str | None
    contact_email: str | None
    status: str


class TenantCommercialProfileCreate(BaseModel):
    tenant_id: int
    plan_id: int | None = None
    reseller_id: int | None = None
    billing_mode: Literal["direct", "reseller_managed"] = "direct"
    seats_purchased: int = 5
    status: Literal["trial", "active", "past_due", "cancelled"] = "trial"


class TenantCommercialProfileRead(ApiModel):
    id: int
    tenant_id: int
    plan_id: int | None
    reseller_id: int | None
    billing_mode: str
    seats_purchased: int
    status: str


class SaaSOverview(BaseModel):
    tenants: int
    active_tenants: int
    resellers: int
    plans: int
    users: int
    companies: int
    reseller_managed_tenants: int


class RoleCreate(BaseModel):
    name: str
    permissions: list[str] = Field(default_factory=list)


class RoleRead(ApiModel):
    id: int
    tenant_id: int
    name: str
    permissions: list[str]


class GoogleSsoConfigure(BaseModel):
    client_id: str | None = None
    encrypted_client_secret_ref: str = "env:IPRL_CAE_GOOGLE_OIDC_CLIENT_SECRET"
    allowed_domains: list[str] = Field(default_factory=list)
    auto_provision: bool = False
    status: Literal["disabled", "active"] = "disabled"


class SsoProviderRead(ApiModel):
    id: int
    tenant_id: int
    provider_key: str
    name: str
    provider_type: str
    issuer: str
    discovery_url: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    userinfo_endpoint: str | None
    client_id: str | None
    scopes: list[str]
    allowed_domains: list[str]
    auto_provision: bool
    status: str


class SsoStartRequest(BaseModel):
    redirect_uri: str
    next_url: str | None = None


class SsoStartResponse(BaseModel):
    provider_key: str
    authorization_url: str
    state: str
    expires_at: datetime


class SsoCallbackRequest(BaseModel):
    state: str
    code: str


class UserIdentityRead(ApiModel):
    id: int
    tenant_id: int
    user_id: int
    identity_provider_id: int
    subject: str
    email: str | None
    email_verified: bool
    hosted_domain: str | None
    last_login_at: datetime | None


class SsoCallbackResponse(BaseModel):
    tenant_id: int
    user: UserRead
    identity: UserIdentityRead
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    next_url: str | None = None


class UserCreate(BaseModel):
    email: str
    name: str
    role_id: int | None = None
    mfa_enabled: bool = False
    status: str = "active"


class UserRead(ApiModel):
    id: int
    tenant_id: int
    email: str
    name: str
    role_id: int | None
    mfa_enabled: bool
    status: str
    email_verified_at: datetime | None = None
    last_login_at: datetime | None = None


class UserCompanyAccessCreate(BaseModel):
    company_id: int
    access_level: Literal["viewer", "editor", "manager", "admin"] = "viewer"
    role_name: str | None = None
    permissions: list[str] = Field(default_factory=list)
    status: str = "active"


class UserCompanyAccessRead(ApiModel):
    id: int
    tenant_id: int
    user_id: int
    company_id: int
    access_level: str
    role_name: str | None
    permissions: list[str]
    status: str


class UserCompanyAccessDetail(UserCompanyAccessRead):
    company_name: str
    company_type: str


class UserPermissionGrantCreate(BaseModel):
    scope_type: Literal["tenant", "company", "platform_account", "system"]
    scope_id: int | None = None
    permission: str
    effect: Literal["allow", "deny"] = "allow"
    reason: str | None = None
    status: Literal["active", "revoked"] = "active"

    @field_validator("permission")
    @classmethod
    def normalize_permission(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized or "." not in normalized:
            raise ValueError("permission must use resource.action format")
        return normalized


class UserPermissionGrantRead(ApiModel):
    id: int
    tenant_id: int
    user_id: int
    scope_type: str
    scope_id: int | None
    permission: str
    effect: str
    reason: str | None
    status: str
    created_by: int | None


class EffectiveCompanyPermissions(BaseModel):
    company_id: int
    company_name: str
    access_level: str | None
    role_name: str | None
    permissions: list[str]
    denied_permissions: list[str]
    sources: list[str]


class UserEffectivePermissions(BaseModel):
    user_id: int
    tenant_id: int
    role_permissions: list[str]
    tenant_permissions: list[str]
    tenant_denied_permissions: list[str]
    company_permissions: list[EffectiveCompanyPermissions]


class CompanyCreate(BaseModel):
    name: str
    tax_id: str | None = None
    company_type: Literal["own", "client", "contractor", "subcontractor"] = "contractor"
    address: str | None = None


class CompanyUpdate(BaseModel):
    name: str
    tax_id: str | None = None
    company_type: Literal["own", "client", "contractor", "subcontractor"] = "contractor"
    address: str | None = None
    status: Literal["active", "inactive"] = "active"


class CompanyRead(ApiModel):
    id: int
    tenant_id: int
    name: str
    tax_id: str | None
    company_type: str
    address: str | None
    status: str


class SignupRequest(BaseModel):
    email: str
    name: str
    password: str = Field(min_length=10)
    tenant_name: str | None = None
    tenant_tax_id: str | None = None
    company_name: str | None = None
    company_tax_id: str | None = None
    company_address: str | None = None


class SignupResponse(BaseModel):
    tenant_id: int
    user_id: int
    company_id: int | None
    email: str
    email_verification_required: bool = True
    verification_url: str | None = None
    dev_verification_token: str | None = None
    message: str


class EmailVerifyRequest(BaseModel):
    token: str


class LoginRequest(BaseModel):
    email: str
    password: str
    tenant_id: int | None = None


class AuthCompanyAccess(BaseModel):
    company_id: int
    company_name: str
    company_type: str
    access_level: str
    permissions: list[str]


class AuthSession(BaseModel):
    tenant_id: int
    user: UserRead
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    company_access: list[AuthCompanyAccess] = Field(default_factory=list)


class AuthMe(BaseModel):
    tenant_id: int
    user: UserRead
    company_access: list[AuthCompanyAccess] = Field(default_factory=list)


class GoogleSignupStartRequest(BaseModel):
    redirect_uri: str
    next_url: str | None = None
    tenant_name: str | None = None
    tenant_tax_id: str | None = None
    company_name: str | None = None
    company_tax_id: str | None = None
    company_address: str | None = None


class GoogleSignupStartResponse(BaseModel):
    authorization_url: str
    state: str
    expires_at: datetime


class GoogleSignupCallbackRequest(BaseModel):
    state: str
    code: str


class CompanyOnboardingRequest(BaseModel):
    name: str
    tax_id: str | None = None
    company_type: Literal["own", "client", "contractor", "subcontractor"] = "own"
    address: str | None = None


class WorkCenterCreate(BaseModel):
    company_id: int
    name: str
    address: str | None = None
    risk_profile_id: str | None = None


class WorkCenterRead(ApiModel):
    id: int
    tenant_id: int
    company_id: int
    name: str
    address: str | None
    risk_profile_id: str | None
    status: str


class WorkerCreate(BaseModel):
    company_id: int
    first_name: str
    last_name: str
    identifier_type: str | None = None
    identifier_value: str | None = None
    identifier_hash: str | None = None
    identifier_last4: str | None = Field(default=None, max_length=4)
    identifier_expires_at: date | None = None
    nationality: str | None = None
    email: str | None = None
    phone: str | None = None
    social_security_number: str | None = None
    social_security_last4: str | None = Field(default=None, max_length=4)
    contract_type: str | None = None
    starts_at: date | None = None
    ends_at: date | None = None
    work_position: str | None = None
    work_center_name: str | None = None
    risk_profile: str | None = None
    employment_status: str = "active"
    medical_fitness_status: str | None = None
    medical_fitness_issued_at: date | None = None
    medical_fitness_expires_at: date | None = None
    medical_fitness_provider: str | None = None
    medical_fitness_restrictions: str | None = None
    cae_notes: str | None = None


class WorkerUpdate(BaseModel):
    company_id: int | None = None
    first_name: str | None = None
    last_name: str | None = None
    identifier_type: str | None = None
    identifier_value: str | None = None
    identifier_hash: str | None = None
    identifier_last4: str | None = Field(default=None, max_length=4)
    identifier_expires_at: date | None = None
    nationality: str | None = None
    email: str | None = None
    phone: str | None = None
    social_security_number: str | None = None
    social_security_last4: str | None = Field(default=None, max_length=4)
    contract_type: str | None = None
    starts_at: date | None = None
    ends_at: date | None = None
    work_position: str | None = None
    work_center_name: str | None = None
    risk_profile: str | None = None
    employment_status: str | None = None
    medical_fitness_status: str | None = None
    medical_fitness_issued_at: date | None = None
    medical_fitness_expires_at: date | None = None
    medical_fitness_provider: str | None = None
    medical_fitness_restrictions: str | None = None
    cae_notes: str | None = None
    status: str | None = None


class WorkerRead(ApiModel):
    id: int
    tenant_id: int
    company_id: int
    first_name: str
    last_name: str
    identifier_type: str | None
    identifier_value: str | None
    identifier_last4: str | None
    identifier_expires_at: date | None
    nationality: str | None
    email: str | None
    phone: str | None
    social_security_number: str | None
    social_security_last4: str | None
    contract_type: str | None
    starts_at: date | None
    ends_at: date | None
    work_position: str | None
    work_center_name: str | None
    risk_profile: str | None
    employment_status: str
    medical_fitness_status: str | None
    medical_fitness_issued_at: date | None
    medical_fitness_expires_at: date | None
    medical_fitness_provider: str | None
    medical_fitness_restrictions: str | None
    cae_notes: str | None
    status: str


class WorkerTrainingCreate(BaseModel):
    course_code: str | None = None
    course_name: str
    provider: str | None = None
    hours: int | None = None
    issued_at: date | None = None
    expires_at: date | None = None
    status: str = "valid_internal"
    document_id: int | None = None
    notes: str | None = None


class WorkerTrainingRead(ApiModel):
    id: int
    tenant_id: int
    worker_id: int
    course_code: str | None
    course_name: str
    provider: str | None
    hours: int | None
    issued_at: date | None
    expires_at: date | None
    status: str
    document_id: int | None
    notes: str | None


class WorkerWorkAssignmentCreate(BaseModel):
    project_id: int | None = None
    work_center_id: int | None = None
    work_name: str
    client_company_name: str | None = None
    role: str | None = None
    starts_at: date | None = None
    ends_at: date | None = None
    status: str = "active"
    source: str = "manual"


class WorkerWorkAssignmentRead(ApiModel):
    id: int
    tenant_id: int
    worker_id: int
    project_id: int | None
    work_center_id: int | None
    work_name: str
    client_company_name: str | None
    role: str | None
    starts_at: date | None
    ends_at: date | None
    status: str
    source: str


class WorkerPlatformRegistrationCreate(BaseModel):
    platform_account_id: int | None = None
    external_platform_id: int | None = None
    platform_name: str
    external_worker_id: str | None = None
    registration_status: str = "not_synced"
    assignment_scope: str | None = None
    source: str = "manual"
    last_synced_at: datetime | None = None
    notes: str | None = None


class WorkerPlatformRegistrationRead(ApiModel):
    id: int
    tenant_id: int
    worker_id: int
    platform_account_id: int | None
    external_platform_id: int | None
    platform_name: str
    external_worker_id: str | None
    registration_status: str
    assignment_scope: str | None
    source: str
    last_synced_at: datetime | None
    notes: str | None


class WorkerBulkImportError(BaseModel):
    row: int
    error: str


class WorkerBulkImportResult(BaseModel):
    source: str
    created: int
    updated: int
    skipped: int
    errors: list[WorkerBulkImportError] = Field(default_factory=list)
    worker_ids: list[int] = Field(default_factory=list)


class WorkerIntakeProposalRead(BaseModel):
    company_id: int
    first_name: str
    last_name: str
    display_name: str
    confidence: int
    status: Literal["new", "existing", "incomplete"]
    intake_ids: list[int] = Field(default_factory=list)
    evidence_filenames: list[str] = Field(default_factory=list)
    notes: str | None = None
    existing_worker_id: int | None = None


class WorkerIntakeImportRequest(BaseModel):
    company_id: int
    dry_run: bool = True
    include_incomplete: bool = True


class WorkerIntakeImportResult(BaseModel):
    source: Literal["document_intake"] = "document_intake"
    dry_run: bool
    created: int
    skipped: int
    proposals: list[WorkerIntakeProposalRead] = Field(default_factory=list)
    worker_ids: list[int] = Field(default_factory=list)


class ErpConnectorRead(BaseModel):
    connector_key: str
    name: str
    status: str
    mode: Literal["mock", "api", "file"]
    dry_run_supported: bool = True
    notes: str


class WorkerErpImportRequest(BaseModel):
    connector_key: str
    company_id: int
    dry_run: bool = True


class WorkerErpImportResult(BaseModel):
    connector_key: str
    dry_run: bool
    created: int
    updated: int
    preview: list[WorkerCreate] = Field(default_factory=list)
    worker_ids: list[int] = Field(default_factory=list)


class DocumentTypeCreate(BaseModel):
    code: str
    name: str
    entity_scope: Literal["company", "worker", "machine", "vehicle", "project"]
    is_common_cae_type: bool = True
    requires_expiration: bool = False
    default_validity_days: int | None = None
    retention_days: int | None = 3650


class DocumentTypeRead(ApiModel):
    id: int
    tenant_id: int | None
    code: str
    name: str
    entity_scope: str
    is_common_cae_type: bool
    requires_expiration: bool
    default_validity_days: int | None
    retention_days: int | None


class DocumentCreate(BaseModel):
    document_type_id: int
    entity_type: Literal["company", "worker", "machine", "vehicle", "project"]
    entity_id: int
    status_internal: str = "draft"


class DocumentRead(ApiModel):
    id: int
    tenant_id: int
    document_type_id: int
    entity_type: str
    entity_id: int
    current_version_id: int | None
    status_internal: str


class DocumentVersionCreate(BaseModel):
    file_storage_key: str
    sha256: str
    filename: str
    mime_type: str = "application/octet-stream"
    size_bytes: int = 0
    issued_at: date | None = None
    expires_at: date | None = None
    platform_expires_at: date | None = None
    expiry_review_status: Literal["ok", "review_required", "reviewed"] = "ok"
    platform_expiry_source: str | None = None
    source: Literal["manual", "api", "rpa", "import", "ocr", "demo"] = "manual"
    created_by: int | None = None

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = value.lower()
        if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
            raise ValueError("sha256 must be a 64-character hexadecimal hash")
        return normalized


class DocumentVersionRead(ApiModel):
    id: int
    document_id: int
    version_number: int
    file_storage_key: str
    sha256: str
    filename: str
    mime_type: str
    size_bytes: int
    issued_at: date | None
    expires_at: date | None
    platform_expires_at: date | None
    expiry_review_status: str
    platform_expiry_source: str | None
    source: str
    created_by: int | None
    created_at: datetime | None = None


class DocumentIntakeRead(ApiModel):
    id: int
    tenant_id: int
    uploaded_by: int | None
    original_filename: str
    file_storage_key: str
    sha256: str
    mime_type: str
    size_bytes: int
    status: str
    intake_scope: str
    requested_company_id: int | None
    requested_worker_id: int | None
    target_notes: str | None
    extraction_engine: str
    extracted_text_excerpt: str | None
    text_confidence: int
    predicted_document_type_id: int | None
    predicted_entity_type: str | None
    predicted_entity_id: int | None
    predicted_company_id: int | None
    predicted_worker_id: int | None
    issued_at: date | None
    expires_at: date | None
    confidence: int
    classification_json: dict[str, Any]
    signals_json: dict[str, Any]
    created_document_id: int | None
    created_version_id: int | None
    review_comment: str | None
    reviewed_at: datetime | None
    created_at: datetime | None = None


class DocumentIntakeBulkSkipped(BaseModel):
    filename: str
    reason: str


class DocumentIntakeBulkUploadRead(BaseModel):
    total_entries: int
    created_count: int
    skipped_count: int
    intakes: list[DocumentIntakeRead]
    skipped: list[DocumentIntakeBulkSkipped]


class DocumentIntakeApprove(BaseModel):
    document_type_id: int | None = None
    entity_type: Literal["company", "worker", "machine", "vehicle", "project"] | None = None
    entity_id: int | None = None
    issued_at: date | None = None
    expires_at: date | None = None
    review_comment: str | None = None


class RequirementProfileCreate(BaseModel):
    name: str
    client_company_id: int | None = None
    work_center_id: int | None = None
    project_id: int | None = None
    activity_code: str | None = None
    risk_level: str | None = None


class RequirementProfileRead(ApiModel):
    id: int
    tenant_id: int
    name: str
    client_company_id: int | None
    work_center_id: int | None
    project_id: int | None
    activity_code: str | None
    risk_level: str | None


class DocumentRequirementCreate(BaseModel):
    document_type_id: int
    entity_scope: Literal["company", "worker", "machine", "vehicle", "project"]
    mandatory: bool = True
    blocks_access: bool = True
    requires_human_validation: bool = True
    expiration_warning_days: int = 30
    validity_rule: str | None = None
    platform_id: int | None = None


class DocumentRequirementRead(ApiModel):
    id: int
    profile_id: int
    document_type_id: int
    entity_scope: str
    mandatory: bool
    blocks_access: bool
    requires_human_validation: bool
    expiration_warning_days: int
    validity_rule: str | None
    platform_id: int | None


class ComplianceItem(BaseModel):
    requirement_id: int
    document_type_id: int
    document_code: str
    document_name: str
    status: str
    blocks_access: bool
    document_id: int | None = None
    document_version_id: int | None = None
    expires_at: date | None = None


class ComplianceSummary(BaseModel):
    entity_type: str
    entity_id: int
    profile_id: int
    overall_status: str
    missing_count: int
    expired_count: int
    rejected_count: int
    expiring_soon_count: int
    valid_count: int
    items: list[ComplianceItem]


class PlatformAccountCreate(BaseModel):
    external_platform_id: int
    display_name: str
    auth_type: str = "manual"
    encrypted_secret_ref: str | None = None
    mode: Literal["disabled", "send", "receive", "send_receive"] = "disabled"
    dry_run: bool = True
    manual_approval_required: bool = True


class PlatformAccountRead(ApiModel):
    id: int
    tenant_id: int
    external_platform_id: int
    display_name: str
    auth_type: str
    mode: str
    dry_run: bool
    manual_approval_required: bool
    status: str


class PlatformConnectionMethodRead(ApiModel):
    id: int
    external_platform_id: int
    method_key: str
    connector_type: str
    connector_key: str | None
    status: str
    implemented: bool
    dry_run_supported: bool
    manual_approval_required: bool
    notes: str | None


class PlatformAccountUserAccessCreate(BaseModel):
    user_id: int
    access_level: Literal["viewer", "operator", "manager", "admin"] = "viewer"
    permissions: list[str] = Field(default_factory=list)
    allowed_operations: list[str] = Field(default_factory=list)
    status: Literal["active", "suspended", "revoked"] = "active"


class PlatformAccountUserAccessRead(ApiModel):
    id: int
    tenant_id: int
    platform_account_id: int
    user_id: int
    access_level: str
    permissions: list[str]
    allowed_operations: list[str]
    status: str


class PlatformAccountUserAccessDetail(PlatformAccountUserAccessRead):
    user_name: str
    user_email: str


class PlatformAdminAccountRead(PlatformAccountRead):
    assigned_users: list[PlatformAccountUserAccessDetail]


class PlatformAdminOverviewRead(ApiModel):
    id: int
    platform_key: str
    name: str
    status: str
    is_commercial: bool
    notes: str | None
    methods: list[PlatformConnectionMethodRead]
    accounts: list[PlatformAdminAccountRead]


class PlatformStandardLabelRead(BaseModel):
    key: str
    category: str
    entity_scope: str
    display_name: str
    description: str
    data_type: str


class PlatformStructureSnapshotCreate(BaseModel):
    external_platform_id: int | None = None
    platform_account_id: int | None = None
    company_id: int | None = None
    platform_label: str
    host: str | None = None
    login_status: str | None = None
    source_type: str = "readonly_capture"
    source_ref: str | None = None
    structure_json: dict[str, Any] = Field(default_factory=dict)
    summary_json: dict[str, Any] = Field(default_factory=dict)


class PlatformStructureSnapshotRead(ApiModel):
    id: int
    tenant_id: int
    external_platform_id: int | None
    platform_account_id: int | None
    company_id: int | None
    platform_label: str
    host: str | None
    login_status: str | None
    source_type: str
    source_ref: str | None
    status: str
    structure_json: dict[str, Any]
    summary_json: dict[str, Any]
    created_by: int | None
    created_at: datetime | None = None


class PlatformDiscoveredLabelRead(ApiModel):
    id: int
    tenant_id: int
    snapshot_id: int
    external_platform_id: int | None
    platform_account_id: int | None
    company_id: int | None
    label_kind: str
    raw_label: str
    normalized_label: str
    page_label: str | None
    entity_scope: str | None
    standard_key: str | None
    confidence: int
    review_status: str
    metadata_json: dict[str, Any]
    notes: str | None


class PlatformDiscoveredLabelUpdate(BaseModel):
    standard_key: str | None = None
    entity_scope: str | None = None
    review_status: Literal["proposed", "approved", "ignored", "needs_review"] | None = None
    notes: str | None = None


class PlatformLabelComparisonItem(BaseModel):
    external_platform_id: int | None
    platform_account_id: int | None
    platform_label: str
    host: str | None
    raw_labels: list[str]
    label_kinds: list[str]
    entity_scopes: list[str]
    review_statuses: list[str]
    count: int


class PlatformLabelComparisonRead(BaseModel):
    standard_key: str
    standard_label: PlatformStandardLabelRead | None
    platform_count: int
    label_count: int
    items: list[PlatformLabelComparisonItem]


class PlatformDataCoveragePendingItemRead(BaseModel):
    id: str
    scope: Literal["account", "category"]
    category_key: str | None
    category_label: str | None
    kind: str
    severity: Literal["green", "orange", "red"]
    standard_key: str | None
    standard_label: str | None
    title: str
    detail: str
    suggested_action: str


class PlatformDataCoverageCategoryRead(BaseModel):
    category_key: str
    label: str
    status: Literal["approved", "mapped", "partial", "missing"]
    mapped_count: int
    approved_count: int
    observed_count: int
    required_count: int
    mapped_keys: list[str]
    approved_keys: list[str]
    observed_keys: list[str]
    pending_review_keys: list[str]
    missing_keys: list[str]
    pending_items: list[PlatformDataCoveragePendingItemRead]


class PlatformDataCoverageContextRead(BaseModel):
    manifest_id: int
    platform_slug: str
    platform_name: str
    account_proposal_id: int | None
    platform_account_id: int | None
    external_company_name: str | None
    trace_label: str
    host: str | None
    entry_url_configured: bool
    manual_approval_required: bool
    dry_run: bool
    categories: list[PlatformDataCoverageCategoryRead]
    blockers: list[str]
    pending_items: list[PlatformDataCoveragePendingItemRead]
    pending_summary: dict[str, int]
    next_action: str
    source_summary: dict[str, Any]


class PlatformDataCoverageRead(BaseModel):
    generated_at: datetime
    safe_mode: dict[str, bool]
    company: dict[str, Any]
    totals: dict[str, int]
    category_contract: list[dict[str, Any]]
    contexts: list[PlatformDataCoverageContextRead]


class PlatformFieldEditEvidenceRead(BaseModel):
    label_id: int | None = None
    raw_label: str | None = None
    label_kind: str | None = None
    page_label: str | None = None
    confidence: int | None = None
    review_status: str | None = None
    source: str | None = None
    input_type: str | None = None
    tag: str | None = None
    required: bool | None = None
    host: str | None = None
    source_ref: str | None = None
    login_status: str | None = None


class PlatformFieldEditMappingCandidateRead(BaseModel):
    mapping_id: int
    mapping_kind: str
    entity_scope: str | None
    external_label: str | None
    external_catalog_value: str | None
    requirement: str | None
    applies_to: str | None
    review_status: str
    status: str


class PlatformFieldEditMethodRead(BaseModel):
    standard_key: str
    display_name: str
    entity_scope: str
    category: str
    data_type: str
    status: Literal[
        "ready_for_preview",
        "needs_editable_capture",
        "needs_mapping_review",
        "needs_mapping",
        "not_external_edit_target",
        "credential_secret_only",
    ]
    method: str
    selector_policy: str
    requires_preview: bool
    requires_manual_approval: bool
    requires_before_after_audit: bool
    sensitive: bool
    observed_labels: list[PlatformFieldEditEvidenceRead]
    mapping_candidates: list[PlatformFieldEditMappingCandidateRead]
    evidence_summary: dict[str, Any]
    next_action: str


class PlatformEditOperationRead(BaseModel):
    operation: str
    status: Literal["ready_for_preview", "needs_editable_capture", "needs_mapping_review", "needs_mapping"]
    required_standard_keys: list[str]
    ready_keys: list[str]
    missing_or_unreviewed_keys: list[str]
    needs_editable_capture_keys: list[str]
    requires_preview: bool
    requires_manual_approval: bool
    requires_before_after_audit: bool
    next_action: str


class PlatformEditMethodsContextRead(BaseModel):
    manifest_id: int
    platform_slug: str
    platform_name: str
    external_platform_id: int | None
    account_proposal_id: int | None
    platform_account_id: int | None
    external_company_name: str | None
    trace_label: str
    host: str | None
    entry_url_configured: bool
    dry_run: bool
    manual_approval_required: bool
    rpa_assisted_on_control: bool
    field_methods: list[PlatformFieldEditMethodRead]
    operations: list[PlatformEditOperationRead]
    source_summary: dict[str, Any]


class PlatformEditMethodsRead(BaseModel):
    generated_at: datetime
    policy: dict[str, Any]
    company: dict[str, Any]
    totals: dict[str, int]
    contexts: list[PlatformEditMethodsContextRead]


class ExchangeWritePreviewRequest(BaseModel):
    operation: Literal[
        "sync_company_profile",
        "upsert_worker",
        "deactivate_worker",
        "upload_worker_document",
        "upload_company_document",
        "upload_machine_vehicle_document",
    ]
    company_id: int | None = None
    worker_id: int | None = None
    document_version_id: int | None = None


class ExchangeWriteSubmitRequest(BaseModel):
    operation: Literal[
        "upsert_worker",
        "upload_worker_document",
        "upload_company_document",
        "upload_machine_vehicle_document",
    ]
    company_id: int | None = None
    worker_id: int | None = None
    document_version_id: int | None = None
    dry_run: bool = True
    manual_approval_required: bool = True
    live_external_write_authorized: bool = False


class ExchangeBulkWorkerSubmitRequest(BaseModel):
    worker_id: int
    company_id: int | None = None
    platform_slugs: list[str] = Field(default_factory=list)
    dry_run: bool = True
    manual_approval_required: bool = True
    live_external_write_authorized: bool = False
    create_capture_requests: bool = False


class ExchangeBulkCaptureWriteScreensRequest(BaseModel):
    platform_slugs: list[str] = Field(default_factory=list)
    include_accounts_without_write_connector: bool = True
    skip_existing_active: bool = True
    request_comment: str | None = Field(default=None, max_length=500)


class ExchangeCaptureWriteScreenRequest(BaseModel):
    request_comment: str | None = Field(default=None, max_length=500)


class ExchangeWritePreviewRead(BaseModel):
    status: str
    operation: str
    platform: dict[str, Any]
    account: dict[str, Any]
    context_trace_label: str | None
    company: dict[str, Any]
    entity: dict[str, Any]
    readiness: dict[str, Any]
    operation_method: dict[str, Any] | None
    fields: list[dict[str, Any]]
    blockers: list[dict[str, str]]
    planned_external_changes: list[dict[str, Any]]
    next_action: str
    policy: dict[str, Any]


class PlatformContractImportRead(BaseModel):
    source_root: str
    priority_group: str
    platform_slugs: list[str]
    manifests_imported: int
    accounts_imported: int
    platform_accounts_upserted: int
    mappings_imported: int
    skipped: list[str]


class PlatformRpaManifestRead(ApiModel):
    id: int
    tenant_id: int
    external_platform_id: int | None
    platform_slug: str
    platform_name: str
    family: str | None
    mode: str
    status: str
    priority_group: str | None
    source_ref: str | None
    schema_version: str | None
    generated_at: str | None
    hosts: list[str]
    entry_urls: list[str]
    allowed_operations: list[str]
    allowed_entity_types: list[str]
    requires_signed_authorization: bool
    dry_run_default: bool
    manual_approval_required: bool
    rpa_assisted_on_control: bool
    sensitive_data_minimization_required: bool
    auxiliary_platform_review_required: bool
    created_by: int | None
    created_at: datetime | None = None


class PlatformRpaAccountProposalRead(ApiModel):
    id: int
    tenant_id: int
    manifest_id: int
    external_platform_id: int | None
    platform_account_id: int | None
    source_platform_account_id: str
    company_source_label: str | None
    source_excel_sheet: str | None
    source_excel_row: int | None
    external_company_name: str | None
    entry_url: str | None
    host: str | None
    user_hint_masked: str | None
    account_status: str
    status: str
    dry_run: bool
    manual_approval_required: bool
    allowed_operations: list[str]
    allowed_entity_types: list[str]
    notes: str | None


class PlatformRpaMappingProposalRead(ApiModel):
    id: int
    tenant_id: int
    manifest_id: int
    external_platform_id: int | None
    mapping_kind: str
    entity_scope: str | None
    iker_key: str
    external_label: str | None
    external_catalog_value: str | None
    requirement: str | None
    applies_to: str | None
    review_status: str
    status: str
    metadata_json: dict[str, Any]
    notes: str | None


class PlatformRpaMappingProposalUpdate(BaseModel):
    external_label: str | None = None
    external_catalog_value: str | None = None
    review_status: Literal["pending_review", "approved", "rejected", "needs_provider_confirmation"] | None = None
    notes: str | None = None


class PlatformContractSummaryRead(BaseModel):
    manifests: int
    accounts: int
    mappings: int
    approved_mappings: int
    pending_mappings: int
    blocked_accounts: int
    priority_platforms: list[str]


class AuthorizationCompanyRead(BaseModel):
    id: int
    name: str
    tax_id: str | None
    status: Literal["green", "orange", "red"]
    summary: str


class AuthorizationTotalsRead(BaseModel):
    platforms: int
    workers: int
    green: int
    orange: int
    red: int
    incidents: int
    red_incidents: int
    orange_incidents: int


class PlatformAuthorizationAccountContextRead(BaseModel):
    account_proposal_id: int
    platform_account_id: int | None
    external_company_name: str | None
    trace_label: str
    status: str
    disabled: bool
    blocked: bool
    has_entry_point: bool


class PlatformAuthorizationRead(BaseModel):
    manifest_id: int
    platform_name: str
    platform_slug: str
    status: Literal["green", "orange", "red"]
    account_count: int
    disabled_account_count: int
    blocked_account_count: int
    mapping_count: int
    approved_mapping_count: int
    worker_green: int
    worker_orange: int
    worker_red: int
    requires_signed_authorization: bool
    dry_run_default: bool
    manual_approval_required: bool
    sensitive_data_minimization_required: bool
    allowed_operations: list[str]
    read_status: Literal["green", "orange", "red"]
    read_summary: str
    read_detail: str
    write_status: Literal["green", "orange", "red"]
    write_summary: str
    write_detail: str
    authorization_status: Literal["green", "orange", "red"]
    authorization_summary: str
    authorization_detail: str
    next_action: str
    local_update_path: str
    account_contexts: list[PlatformAuthorizationAccountContextRead] = Field(default_factory=list)


class WorkerPlatformAuthorizationRegistrationRead(BaseModel):
    id: int
    platform_name: str
    external_worker_id: str | None
    registration_status: str
    registration_status_color: Literal["green", "orange", "red"]
    assignment_scope: str | None
    source: str
    last_synced_at: datetime | None
    notes: str | None


class WorkerAuthorizationRead(BaseModel):
    worker_id: int
    worker_name: str
    company_id: int
    status: Literal["green", "orange", "red"]
    identifier_present: bool
    medical_fitness_status: str | None
    documents: int
    platform_registrations: int
    platform_registration_details: list[WorkerPlatformAuthorizationRegistrationRead] = Field(default_factory=list)
    incident_count: int
    local_update_path: str


class AuthorizationIncidentRead(BaseModel):
    incident_key: str
    severity: Literal["green", "orange", "red"]
    platform_name: str | None
    entity_type: str
    entity_id: int
    title: str
    detail: str
    suggested_action: str
    local_update_path: str
    source: str


class PlatformAuthorizationDashboardRead(BaseModel):
    generated_at: datetime
    company: AuthorizationCompanyRead
    overall_status: Literal["green", "orange", "red"]
    totals: AuthorizationTotalsRead
    platforms: list[PlatformAuthorizationRead]
    workers: list[WorkerAuthorizationRead]
    incidents: list[AuthorizationIncidentRead]


class ExternalDocumentStatusRead(BaseModel):
    id: int
    tenant_id: int
    external_platform_id: int
    platform_key: str
    platform_name: str
    document_id: int
    document_version_id: int
    document_type_code: str
    document_type_name: str
    entity_type: str
    entity_id: int
    entity_name: str | None
    status: str
    status_color: Literal["green", "orange", "red"]
    external_comment: str | None
    external_document_id: str | None
    external_requirement_id: str | None
    last_checked_at: datetime


class PlatformReviewScheduleRead(BaseModel):
    id: int
    tenant_id: int
    manifest_id: int
    external_platform_id: int | None
    platform_slug: str
    platform_name: str
    priority_group: str | None
    enabled: bool
    interval_minutes: int
    review_scope: list[str]
    status: str
    dry_run: bool
    manual_approval_required: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    last_result_status: str | None
    last_result_summary: str | None
    notes: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PlatformReviewScheduleUpdate(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = Field(default=None, ge=15, le=43200)
    review_scope: list[Literal["company", "workers", "documents", "incidents", "mappings"]] | None = None
    status: Literal["disabled", "scheduled", "paused"] | None = None
    notes: str | None = None


class PlatformReviewHealthTotals(BaseModel):
    platforms: int
    working: int
    not_working: int
    not_configured: int
    not_checked: int


class PlatformReviewHealthPlatform(BaseModel):
    schedule_id: int
    manifest_id: int
    platform_slug: str
    platform_name: str
    enabled: bool
    interval_minutes: int
    configured_every_12h: bool
    connector_available: bool
    dry_run: bool
    manual_approval_required: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    last_result_status: str | None
    last_result_summary: str | None
    review_status: Literal["working", "not_working", "not_configured", "not_checked"]
    status_color: Literal["green", "orange", "red"]
    working: list[str]
    not_working: list[str]


class PlatformReviewHealthRead(BaseModel):
    generated_at: datetime
    priority_group: str | None
    interval_minutes_required: int
    safe_mode: bool
    totals: PlatformReviewHealthTotals
    summary: str
    platforms: list[PlatformReviewHealthPlatform]


class RpaVariantItemRead(BaseModel):
    key: str
    label: str
    status: str
    purpose: str
    next_action: str
    evidence: list[str]
    stop_conditions: list[str]


class RpaVariantMappingSummaryRead(BaseModel):
    total: int
    approved: int
    pending_review: int
    by_kind: dict[str, int]


class RpaVariantArmSnapshotRead(BaseModel):
    company_id: int | None
    company_name: str | None
    workers: int
    company_documents: int
    worker_documents: int
    pending_intakes: int
    platform_registrations: int
    external_statuses: int


class RpaVariantPlanTotalsRead(BaseModel):
    platforms: int
    accounts: int
    credential_ready_accounts: int
    entry_ready_accounts: int
    gateway_ready_platforms: int
    implemented_read_connectors: int


class RpaVariantPlatformPlanRead(BaseModel):
    manifest_id: int
    external_platform_id: int | None
    platform_slug: str
    platform_name: str
    priority_group: str | None
    hosts: list[str]
    account_count: int
    credential_ready_accounts: int
    entry_ready_accounts: int
    schedule_id: int | None
    schedule_status: str
    last_result_status: str | None
    last_result_summary: str | None
    implemented_connector_available: bool
    gateway_ready: bool
    login_variants: list[RpaVariantItemRead]
    context_variants: list[RpaVariantItemRead]
    read_variants: list[RpaVariantItemRead]
    mapping_summary: RpaVariantMappingSummaryRead
    safe_attempt_policy: dict[str, Any]
    blockers: list[str]
    next_action: str


class RpaVariantPlanRead(BaseModel):
    generated_at: datetime
    priority_group: str | None
    safe_mode: bool
    policy: dict[str, Any]
    arm_snapshot: RpaVariantArmSnapshotRead
    totals: RpaVariantPlanTotalsRead
    platforms: list[RpaVariantPlatformPlanRead]


class PlatformReviewRunRequest(BaseModel):
    account_proposal_id: int | None = None


class PlatformReviewRunRead(BaseModel):
    id: int
    tenant_id: int
    schedule_id: int
    manifest_id: int
    account_proposal_id: int | None
    external_platform_id: int | None
    platform_slug: str
    platform_name: str
    operation: str
    trigger_source: str
    status: str
    dry_run: bool
    manual_approval_required: bool
    started_at: datetime | None
    finished_at: datetime | None
    result_status: str | None
    result_summary: str | None
    error_summary: str | None
    evidence_json: dict[str, Any]
    created_at: datetime | None = None


class RpaGatewayActionRead(BaseModel):
    action_key: str
    label: str
    description: str
    enabled: bool
    writes_external_system: bool


class RpaGatewayScheduleRead(BaseModel):
    schedule_id: int
    manifest_id: int
    platform_slug: str
    platform_name: str
    enabled: bool
    dry_run: bool
    manual_approval_required: bool
    last_result_status: str | None
    next_run_at: datetime | None
    human_assisted_supported: bool


class RpaGatewayOptionsRead(BaseModel):
    actions: list[RpaGatewayActionRead]
    schedules: list[RpaGatewayScheduleRead]
    policy: dict[str, bool]


class RpaGatewayRequestCreate(BaseModel):
    schedule_id: int | None = None
    manifest_id: int | None = None
    account_proposal_id: int | None = None
    action_key: Literal["read_external_status", "capture_write_screen"]
    request_comment: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_schedule_or_manifest(self) -> RpaGatewayRequestCreate:
        if self.schedule_id is None and self.manifest_id is None:
            raise ValueError("schedule_id or manifest_id is required.")
        return self


class RpaGatewayDecisionCreate(BaseModel):
    decision: Literal["authorize_enter_page", "human_control_resolved", "cancel"]
    notes: str | None = Field(default=None, max_length=500)


class RpaGatewayBrowserLaunchRead(BaseModel):
    run_id: int
    launched: bool
    status: str
    message: str
    pid: int | None
    credential_available: bool
    entry_url: str | None
    status_artifact: str | None
    session_persistence: dict[str, Any] | None = None


class RpaGatewayBrowserStatusRead(BaseModel):
    run_id: int
    available: bool
    state: str
    message: str
    updated_at_utc: str | None = None
    platform_label: str | None = None
    entry_url: str | None = None
    selected_login_variant: str | None = None
    login_variant_policy: dict[str, Any] | None = None
    capture_summary: dict[str, Any] | None = None
    session_persistence: dict[str, Any] | None = None


class RpaGatewayCaptureSyncRead(BaseModel):
    run_id: int
    synced: bool
    status: str
    message: str
    pages_captured: int
    status_counts: list[Any] = Field(default_factory=list)
    persisted_row_level: bool = False
    row_level_blocker: str | None = None


class SystemPlatformModuleRead(BaseModel):
    platform_key: str
    platform_name: str
    method_key: str
    connector_type: str
    connector_key: str | None
    module_scope: Literal["system"] = "system"
    implemented: bool
    status: str
    health_status: str
    health_message: str
    dry_run_supported: bool
    manual_approval_required: bool
    tenant_config_required: bool
    notes: str


class TransferRequest(BaseModel):
    platform_key: str
    connector_key: Literal[
        "connector_demo",
        "connector_manual_export",
        "connector_rpa_e_coordina_write",
        "connector_rpa_ctaima_write",
        "connector_rpa_seisconecta_write",
        "connector_rpa_nomio_write",
        "connector_rpa_timenet_write",
        "connector_rpa_validate_write",
        "connector_rpa_vitaly_cae_write",
    ]
    operation: Literal[
        "upload_document",
        "generate_manual_export",
        "upsert_worker",
        "upload_worker_document",
        "upload_company_document",
        "upload_machine_vehicle_document",
    ] = "upload_document"
    document_version_id: int | None = None
    worker_id: int | None = None
    account_proposal_id: int | None = None
    dry_run: bool = True
    manual_approval_required: bool = True
    live_external_write_authorized: bool = False


class TransferRead(ApiModel):
    id: int
    tenant_id: int
    external_platform_id: int | None
    connector_key: str
    operation: str
    status: str
    dry_run: bool
    requires_approval: bool
    idempotency_key: str | None
    error_summary: str | None
    created_at: datetime | None = None
    last_attempt_status: str | None = None
    last_attempt_message: str | None = None
    post_write_read_confirmed: bool | None = None
    valid_external_write: bool | None = None
    status_artifact: str | None = None


class AuditLogRead(ApiModel):
    id: int
    tenant_id: int | None
    action: str
    entity_type: str
    entity_id: str | None
    before_json: dict[str, Any] | None
    after_json: dict[str, Any] | None
    correlation_id: str | None
    created_at: datetime | None = None


class DashboardSummary(BaseModel):
    tenant_id: int
    company_id: int | None = None
    companies: int
    workers: int
    documents: int
    valid_documents: int
    expired_documents: int
    expiring_soon_documents: int
    pending_transfer_jobs: int
    failed_transfer_jobs: int
    platforms_cataloged: int


class CompanyDashboardSummary(BaseModel):
    tenant_id: int
    company_id: int
    company_name: str
    company_type: str
    workers: int
    documents: int
    valid_documents: int
    expired_documents: int
    expiring_soon_documents: int
