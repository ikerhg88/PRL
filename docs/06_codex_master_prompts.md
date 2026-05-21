# 06 — Prompts maestros para Codex

## Prompt 1 — Inicialización del monorepo

```text
Lee AGENTS.md y toda la carpeta docs/ antes de escribir código.

Crea un monorepo para IKER PRL/CAE Hub con:
- backend FastAPI
- frontend Next.js TypeScript
- PostgreSQL
- Redis
- Servicios independientes del servidor, sin Docker ni contenedores
- Alembic
- pytest
- Makefile

Primera entrega:
1. Estructura de carpetas.
2. Backend con healthcheck.
3. Frontend con dashboard mínimo.
4. Arranque funcional como servicios independientes, sin Docker ni contenedores.
5. README con instalación.
6. AGENTS.md respetado.

No implementes conectores reales ni endpoints de plataformas comerciales.
Crea solo connector_demo y connector_manual_export.
Ejecuta tests y deja constancia de resultados.
```

## Prompt 2 — Modelo de datos y migraciones

```text
Implementa el modelo de datos descrito en docs/03_data_model.md.

Requisitos:
- SQLAlchemy 2.x o SQLModel.
- Alembic.
- Migración inicial.
- Seeds de catálogo documental CAE común.
- Separación por tenant.
- Tests de creación y relaciones.

Incluye al menos:
Tenant, User, Company, WorkCenter, Project, Worker, Machine, Vehicle, DocumentType, Document, DocumentVersion, RequirementProfile, DocumentRequirement, ExternalPlatform, PlatformAccount, PlatformEntityMapping, PlatformRequirementMapping, TransferJob, TransferAttempt, ExternalDocumentStatus, AuditLog.

No guardar datos médicos completos. Para aptitud médica usar solo estado, fecha y documento mínimo.
```

## Prompt 3 — CRUD y gestión documental

```text
Crea endpoints REST y UI mínima para:
- Empresas
- Centros
- Trabajadores
- Tipos de documento
- Documentos y versiones
- Caducidades

Requisitos:
- Subida de fichero con hash SHA-256.
- Emisión/caducidad.
- Estado documental interno.
- Auditoría de creación, actualización y subida.
- Tests backend.
- Pantallas frontend básicas.
```

## Prompt 4 — Motor de requisitos

```text
Implementa el motor de requisitos PRL/CAE.

Debe calcular:
- Estado por documento requerido.
- Estado por trabajador.
- Estado por empresa.
- Estado por perfil/centro/proyecto.
- Semáforo global.

Estados:
missing, draft, pending_internal_review, valid_internal, expiring_soon, expired, rejected_internal, not_applicable.

Incluye alertas de caducidad y tests unitarios exhaustivos.
```

## Prompt 5 — Framework de conectores

```text
Implementa el framework de conectores de docs/04_connector_framework.md.

Crear:
- Interfaz abstracta CoordinationPlatformConnector.
- Connector registry.
- Transfer jobs.
- Modo dry_run.
- Aprobación manual.
- Idempotency keys.
- Redacción de secretos en logs.
- connector_demo.
- connector_manual_export.

No crear conectores reales todavía.
No inventar APIs externas.
```

## Prompt 6 — Exportación asistida

```text
Crea connector_manual_export.

Debe generar:
- ZIP con documentos seleccionados.
- Excel con metadatos: entidad, documento, emisión, caducidad, hash, plataforma destino, requisito.
- README del lote.
- Checklist de subida.
- Registro de auditoría.

Debe poder exportar por empresa, trabajador, centro, proyecto y plataforma.
```

## Prompt 7 — RPA autorizada base

```text
Crea la base del módulo de RPA autorizada descrito en docs/05_authorized_rpa_playbook.md.

Importante:
- No activar por defecto.
- No incluir técnicas stealth.
- No implementar bypass de captcha/MFA.
- No usar proxies.
- No inventar selectores de plataformas reales.
- Implementar plataforma demo local para pruebas.

Debe incluir:
- Manifest loader YAML.
- Consent/authorization policy.
- Preflight.
- Plan de acciones.
- Aprobación humana.
- Playwright contra portal demo local.
- Tests e2e demo.
```

## Prompt 8 — Panel de transferencias inspirado en Konvergia

```text
Implementa un panel de transferencias con columnas:
- fecha/hora
- empresa/trabajador
- origen
- destino
- tipo documental
- fichero
- código documental
- estado
- resultado externo
- job ID

Debe filtrar por plataforma, entidad, documento, estado y rango temporal.
Debe basarse en TransferJob, TransferAttempt y ExternalDocumentStatus.
```

## Prompt 9 — Seguridad y privacidad

```text
Implementa controles mínimos de seguridad:
- RBAC.
- Cifrado de secretos.
- Redacción de logs.
- Auditoría append-only.
- Política de retención documental.
- Tests de no filtrado de secretos.
- Validación de permisos por tenant.

Lee docs/07_security_privacy_rgpd.md antes de empezar.
```

## Prompt 10 — Preparación de conectores reales

```text
Prepara una unica plataforma local mock:
- mock_cae

El mock debe contener:
- README con estado: sin implementación real.
- manifest de prueba en dry_run.
- lista de información requerida para activar una integracion comercial futura.
- tests que verifiquen que no se ejecuta sin configuración/autorización.

No usar scraping real ni endpoints reales todavía.
```
