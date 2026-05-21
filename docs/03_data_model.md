# 03 — Modelo de datos inicial

## 1. Entidades principales

### Tenant

Representa una organización usuaria de IKER.

Campos:

- `id`.
- `name`.
- `tax_id`.
- `status`.
- `created_at`.
- `updated_at`.

### User

- `id`.
- `tenant_id`.
- `email`.
- `name`.
- `password_hash` nullable para usuarios SSO-only.
- `role_id`.
- `mfa_enabled`.
- `status`.
- `email_verified_at`.
- `last_login_at`.

### EmailVerificationToken

Token de verificacion de email para signup local.

- `id`.
- `tenant_id`.
- `user_id`.
- `token_hash`: SHA-256 del token, nunca token en claro.
- `purpose`: signup_email_verification.
- `expires_at`.
- `consumed_at`.
- `created_at`.

### Role / Permission

- Roles por tenant.
- Permisos granulares: lectura, escritura, validación, administración, conectores, auditoría.

### UserPermissionGrant

Override granular de permisos por usuario. Complementa roles y accesos multiempresa.

- `id`.
- `tenant_id`.
- `user_id`.
- `scope_type`: tenant, company, platform_account, system.
- `scope_id` nullable para tenant/system.
- `permission`: formato `recurso.accion`.
- `effect`: allow, deny.
- `reason`.
- `status`: active, revoked.
- `created_by`.

### OauthSignupState

Estado temporal para signup SaaS con Google OIDC antes de que exista el tenant definitivo.

- `id`.
- `state`.
- `nonce`.
- `code_verifier`.
- `redirect_uri`.
- `next_url`.
- `tenant_name`.
- `tenant_tax_id`.
- `company_name`.
- `company_tax_id`.
- `company_address`.
- `expires_at`.
- `consumed_at`.
- `created_at`.

### Company

- `id`.
- `tenant_id`.
- `name`.
- `tax_id`.
- `company_type`: own, client, contractor, subcontractor.
- `address`.
- `status`.

### WorkCenter

- `id`.
- `tenant_id`.
- `company_id`.
- `name`.
- `address`.
- `risk_profile_id`.

### Project / Contract

- Proyecto, obra o contrato asociado a cliente/centro.
- Fechas de inicio/fin.
- Actividad.
- Estado.

### Worker

- `id`.
- `tenant_id`.
- `company_id`.
- `first_name`.
- `last_name`.
- `identifier_type`.
- `identifier_value`.
- `identifier_hash`.
- `identifier_last4`.
- `identifier_expires_at`.
- `nationality`.
- `email`.
- `phone`.
- `social_security_number`.
- `social_security_last4`.
- `contract_type`.
- `starts_at`.
- `ends_at`.
- `work_position`.
- `work_center_name`.
- `risk_profile`.
- `employment_status`.
- `medical_fitness_status`.
- `medical_fitness_issued_at`.
- `medical_fitness_expires_at`.
- `medical_fitness_provider`.
- `medical_fitness_restrictions`.
- `cae_notes`.
- `status`.

Nota: el producto permite mostrar y operar con DNI/NAF completos cuando el cliente confirma base legal/autorizacion. Aun asi debe mantenerse control de acceso, auditoria y cifrado en despliegues productivos.

### WorkerTraining

Cursos y formacion PRL vinculados a un trabajador.

- `id`.
- `tenant_id`.
- `worker_id`.
- `course_code`.
- `course_name`.
- `provider`.
- `hours`.
- `issued_at`.
- `expires_at`.
- `status`.
- `document_id`.
- `notes`.

### WorkerWorkAssignment

Obras, centros o proyectos donde participa un trabajador.

- `id`.
- `tenant_id`.
- `worker_id`.
- `project_id`.
- `work_center_id`.
- `work_name`.
- `client_company_name`.
- `role`.
- `starts_at`.
- `ends_at`.
- `status`.
- `source`: manual, bulk_csv, erp, connector.

### WorkerPlatformRegistration

Presencia del trabajador en una plataforma/cuenta externa.

- `id`.
- `tenant_id`.
- `worker_id`.
- `platform_account_id`.
- `external_platform_id`.
- `platform_name`.
- `external_worker_id`.
- `registration_status`.
- `assignment_scope`.
- `source`.
- `last_synced_at`.
- `notes`.

### Machine / Vehicle

- `id`.
- `tenant_id`.
- `company_id`.
- `type`.
- `brand`.
- `model`.
- `serial_number`.
- `plate_number`.
- `status`.

### DocumentType

- `id`.
- `tenant_id` nullable para catálogo global.
- `code`.
- `name`.
- `entity_scope`: company, worker, machine, vehicle, project.
- `is_common_cae_type`.
- `requires_expiration`.
- `default_validity_days`.

### Document

- `id`.
- `tenant_id`.
- `document_type_id`.
- `entity_type`.
- `entity_id`.
- `current_version_id`.
- `status_internal`.

### DocumentVersion

- `id`.
- `document_id`.
- `version_number`.
- `file_storage_key`.
- `sha256`.
- `filename`.
- `mime_type`.
- `size_bytes`.
- `issued_at`.
- `expires_at`: caducidad declarada por la empresa.
- `platform_expires_at`: caducidad comunicada por una plataforma externa.
- `expiry_review_status`: ok, review_required, reviewed.
- `platform_expiry_source`.
- `source`: manual, api, rpa, import, ocr, demo.
- `created_by`.
- `created_at`.

### DocumentIntake

Buzon OCR previo a crear una version documental.

- `id`.
- `tenant_id`.
- `uploaded_by`.
- `original_filename`.
- `file_storage_key`.
- `sha256`.
- `mime_type`.
- `size_bytes`.
- `status`: pending_review, accepted, rejected.
- `intake_scope`: auto, company, single_worker, multiple_workers.
- `requested_company_id`.
- `requested_worker_id`.
- `target_notes`.
- `extraction_engine`.
- `extracted_text_excerpt` redaccionado.
- `text_confidence`.
- `predicted_document_type_id`.
- `predicted_entity_type`.
- `predicted_entity_id`.
- `predicted_company_id`.
- `predicted_worker_id`.
- `issued_at`.
- `expires_at`.
- `confidence`.
- `classification_json`.
- `signals_json`.
- `created_document_id`.
- `created_version_id`.
- `review_comment`.
- `reviewed_at`.

### Validation

- `id`.
- `document_version_id`.
- `validator_id`.
- `status`.
- `comment`.
- `validated_at`.

### RequirementProfile

- `id`.
- `tenant_id`.
- `name`.
- `client_company_id`.
- `work_center_id`.
- `project_id`.
- `activity_code`.
- `risk_level`.

### DocumentRequirement

- `id`.
- `profile_id`.
- `document_type_id`.
- `entity_scope`.
- `mandatory`.
- `blocks_access`.
- `requires_human_validation`.
- `expiration_warning_days`.
- `validity_rule`.
- `platform_id` nullable.

### ExternalPlatform

Catalogo global del sistema, no configuracion propia de un tenant.

- `id`.
- `name`.
- `platform_key`.
- `connector_type`: api, rpa, export, demo.
- `status`.

En la version actual solo se activa operativamente `mock_cae`. Las plataformas comerciales investigadas se catalogan como referencia tecnica y preparacion de conectores, pero sus metodos API/RPA permanecen sin implementar hasta que exista autorizacion, credenciales y documentacion oficial. La investigacion viva esta en `docs/09_platform_api_research.md`.

### PlatformAccount

Configuracion propia del tenant para usar una plataforma catalogada.

- `id`.
- `tenant_id`.
- `external_platform_id`.
- `display_name`.
- `auth_type`.
- `encrypted_secret_ref`.
- `mode`: disabled, send, receive, send_receive.
- `dry_run`.
- `manual_approval_required`.

### PlatformAccountUserAccess

Asignacion de usuarios internos a una cuenta/configuracion de plataforma.

- `id`.
- `tenant_id`.
- `platform_account_id`.
- `user_id`.
- `access_level`: viewer, operator, manager, admin.
- `permissions`.
- `allowed_operations`.
- `status`: active, suspended, revoked.

### PlatformEntityMapping

- `id`.
- `tenant_id`.
- `external_platform_id`.
- `local_entity_type`.
- `local_entity_id`.
- `external_entity_id`.
- `external_url`.
- `confidence`.
- `last_seen_at`.

### PlatformRequirementMapping

- `id`.
- `tenant_id`.
- `external_platform_id`.
- `local_document_type_id`.
- `external_requirement_id`.
- `external_requirement_name`.
- `direction`: send, receive, both.

### TransferJob

- `id`.
- `tenant_id`.
- `platform_account_id`.
- `operation`.
- `status`.
- `dry_run`.
- `requires_approval`.
- `approved_by`.
- `approved_at`.
- `started_at`.
- `finished_at`.
- `error_summary`.

### TransferAttempt

- `id`.
- `transfer_job_id`.
- `attempt_number`.
- `status`.
- `request_metadata`.
- `response_metadata`.
- `evidence_storage_key`.
- `created_at`.

### ExternalDocumentStatus

- `id`.
- `tenant_id`.
- `external_platform_id`.
- `document_version_id`.
- `external_document_id`.
- `external_requirement_id`.
- `status`.
- `external_comment`.
- `last_checked_at`.

### AuditLog

- `id`.
- `tenant_id`.
- `actor_user_id`.
- `action`.
- `entity_type`.
- `entity_id`.
- `before_json`.
- `after_json`.
- `correlation_id`.
- `created_at`.

## 2. Relaciones críticas

- Un `Document` pertenece a una entidad concreta.
- Un `Document` tiene muchas `DocumentVersion`.
- Una `DocumentVersion` puede tener muchos estados externos.
- Un `RequirementProfile` contiene múltiples requisitos.
- Un requisito puede estar ligado a una plataforma concreta o ser global.
- Un `PlatformAccount` tiene mappings propios por tenant.
- Un `Worker` puede tener muchas obras/centros y muchas altas en plataformas.
- Los permisos efectivos de un usuario se calculan cruzando rol, accesos a empresa, grants granulares allow/deny y scope.

## 3. Semáforos

### WorkerComplianceSnapshot

Tabla materializada o vista calculada:

- `worker_id`.
- `profile_id`.
- `overall_status`.
- `missing_count`.
- `expired_count`.
- `rejected_count`.
- `expiring_soon_count`.
- `platform_status_summary`.
- `calculated_at`.

## 4. Códigos documentales

Adoptar formato interno:

```text
CAE.COMPANY.RC_POLICY
CAE.COMPANY.RC_RECEIPT
CAE.COMPANY.AEAT_CLEARANCE
CAE.COMPANY.SS_CLEARANCE
CAE.COMPANY.RLC_TC1
CAE.COMPANY.RNT_TC2
CAE.COMPANY.ITA
CAE.WORKER.ID_DOCUMENT
CAE.WORKER.MEDICAL_FITNESS
CAE.WORKER.PPE_DELIVERY
CAE.WORKER.BASIC_PRL_COURSE
CAE.WORKER.RISK_INFORMATION
```

Los códigos externos se mapearán por plataforma.
