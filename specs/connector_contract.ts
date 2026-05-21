export type EntityType = "company" | "worker" | "machine" | "vehicle" | "project";

export type ConnectorMode = "disabled" | "send" | "receive" | "send_receive";

export type ConnectorKind = "api" | "rpa" | "manual_export" | "demo";

export type NormalizedExternalStatus =
  | "not_synced"
  | "queued"
  | "submitted"
  | "pending_external_validation"
  | "accepted"
  | "accepted_with_warnings"
  | "rejected"
  | "expired_external"
  | "unknown"
  | "manual_required"
  | "blocked_by_platform";

export interface ConnectorContext {
  tenantId: string;
  platformAccountId: string;
  dryRun: boolean;
  manualApprovalRequired: boolean;
  correlationId: string;
}

export interface AuthResult {
  ok: boolean;
  expiresAt?: string;
  message?: string;
}

export interface HealthCheck {
  ok: boolean;
  connectorKind: ConnectorKind;
  platformKey: string;
  message?: string;
}

export interface ExternalRef {
  externalId: string;
  externalUrl?: string;
  confidence?: number;
}

export interface ExternalCatalog {
  documentTypes: Array<{
    externalRequirementId: string;
    externalName: string;
    normalizedDocumentTypeCode?: string;
    entityScope: EntityType;
  }>;
}

export interface UploadDocumentInput {
  localDocumentVersionId: string;
  sha256: string;
  filename: string;
  mimeType: string;
  targetEntityType: EntityType;
  targetEntityId: string;
  externalRequirementId: string;
  idempotencyKey: string;
}

export interface UploadResult {
  status: NormalizedExternalStatus;
  externalDocumentId?: string;
  externalUrl?: string;
  message?: string;
  evidenceId?: string;
}

export interface DocumentStatusResult {
  status: NormalizedExternalStatus;
  externalDocumentId?: string;
  externalComment?: string;
  checkedAt: string;
}

export interface AccessStatusResult {
  status: "allowed" | "blocked" | "unknown";
  reason?: string;
  checkedAt: string;
}

export interface CoordinationPlatformConnector {
  platformId: string;
  connectorKind: ConnectorKind;

  authenticate(ctx: ConnectorContext): Promise<AuthResult>;
  testConnection(ctx: ConnectorContext): Promise<HealthCheck>;
  syncCatalog(ctx: ConnectorContext): Promise<ExternalCatalog>;

  upsertCompany(ctx: ConnectorContext, companyId: string): Promise<ExternalRef>;
  upsertWorker(ctx: ConnectorContext, workerId: string): Promise<ExternalRef>;
  upsertMachine(ctx: ConnectorContext, machineId: string): Promise<ExternalRef>;
  upsertVehicle(ctx: ConnectorContext, vehicleId: string): Promise<ExternalRef>;

  uploadDocument(ctx: ConnectorContext, input: UploadDocumentInput): Promise<UploadResult>;
  getDocumentStatus(ctx: ConnectorContext, externalDocumentId: string): Promise<DocumentStatusResult>;
  getAccessStatus(ctx: ConnectorContext, entityType: EntityType, entityId: string): Promise<AccessStatusResult>;
}
