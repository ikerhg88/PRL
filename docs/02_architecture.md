# 02 — Arquitectura técnica propuesta

## 1. Vista general

IKER se compone de cinco capas:

1. Frontend web.
2. Backend API.
3. Base de datos y almacenamiento documental.
4. Motor de reglas y jobs.
5. Conectores externos.

```text
[Next.js Frontend]
       |
[FastAPI Backend] ---- [PostgreSQL]
       |                  |
       |              [Audit Log]
       |
[Document Storage] -- [OCR/Extraction]
       |
[Job Queue: Redis/Celery]
       |
[Connector Registry]
       |------ API connectors
       |------ Authorized RPA connectors
       |------ Manual export connectors
       |------ Demo connectors
```

## 2. Backend

- FastAPI.
- SQLAlchemy 2.x / SQLModel.
- Pydantic para esquemas.
- Alembic para migraciones.
- Autenticación JWT/OIDC.
- RBAC.
- Configuracion runtime desde `config/iprl-cae.config.toml` o `IPRL_CAE_CONFIG_FILE`, siempre sin secretos reales en el fichero versionado.
- Las variables `IPRL_CAE_*` y `.env` tienen prioridad sobre TOML para despliegue y secretos.
- Servicios separados:
  - `identity_service`.
  - `document_service`.
  - `requirement_service`.
  - `connector_service`.
  - `audit_service`.
  - `notification_service`.

## 3. Frontend

- Next.js + TypeScript.
- `AppShell` global para todas las rutas operativas con navegacion agrupada por ARM y Operativa. Las rutas de autenticacion, seleccion de empresa, verificacion, callback OIDC y onboarding no muestran el shell operativo.
- Rutas principales:
  - `/login`.
  - `/verify-email`.
  - `/auth/google/callback`.
  - `/onboarding/company`.
  - `/select-company`.
  - `/`.
  - `/arm`.
  - `/platforms`.
  - `/assign-worker`.
  - `/notifications`.
  - `/rpa-gateway`.

## 4. Jobs

Cada operación externa debe ejecutarse como job asíncrono:

- `sync_catalog`.
- `upsert_company`.
- `upsert_worker`.
- `upsert_machine`.
- `upload_document`.
- `poll_document_status`.
- `generate_manual_export`.
- `rpa_preflight`.
- `rpa_submit_with_approval`.

## 5. Conector API

Usa API oficial/documentada. Requisitos:

- InverburTTP tipado.
- Autenticación segura.
- Idempotency keys.
- Reintentos.
- Rate limiting.
- Logs sin secretos.
- Sandbox si existe.

## 6. Conector RPA autorizado

Automatización de navegador para operaciones permitidas por el titular de la cuenta y condiciones aplicables.

Componentes:

- Playwright.
- Vault de credenciales.
- Sesiones controladas.
- Selector registry por versión de plataforma.
- Preflight de login y navegación.
- Plan de acciones antes de escribir.
- Aprobación humana previa.
- Captura de evidencias permitidas.
- Rate limiting.
- Circuit breaker.

No se implementará:

- Bypass de captcha/MFA.
- Técnicas stealth.
- Proxy rotation.
- Scraping de áreas no autorizadas.
- Explotación de endpoints privados.
- Automatización para eludir licencias o controles contractuales.

## 7. Exportación asistida

Fallback universal:

- ZIP con documentos.
- Excel/CSV de metadatos.
- README de lote.
- Checklist por plataforma.
- Mapeo de requisitos.
- Evidencia de preparación.

## 8. Almacenamiento documental

- Hash SHA-256.
- Versiones inmutables.
- Metadatos indexados.
- Antivirus opcional.
- Retención configurable.
- Borrado lógico y purga segura.

## 9. Auditoría

Tabla append-only:

- Actor.
- Tenant.
- Acción.
- Entidad.
- Antes/después cuando proceda.
- IP/device.
- Job asociado.
- Resultado.
- Correlation ID.

## 10. Observabilidad

- Logs estructurados.
- Métricas de jobs.
- Alertas de fallos.
- Trazas por conector.
- Dashboard de sincronización.

## 11. Separacion tenant/sistema

Rutas de tenant/empresa:

- `/auth/signup`, `/auth/login`, `/auth/verify-email`, `/auth/me`: identidad local, verificacion y sesion JWT.
- `/auth/google/signup/*`: signup SaaS con Google OIDC antes de crear tenant.
- `/auth/companies/onboarding`: alta de empresa posterior al signup.
- `/tenant-platforms/*`: cuentas de plataforma del tenant, usuarios asignados, permisos y operaciones permitidas.
- `/platforms/accounts/*`: alias compatible, no recomendado para nueva UI.

Rutas de sistema:

- `/system/platform-modules`: modulos tecnicos instalados, implementacion y health.
- `/platforms/catalog`: catalogo tecnico global de plataformas, sin datos de tenant y sin exposicion en la navegacion diaria.

Las rutas de sistema no almacenan credenciales ni documentos de clientes. Las rutas de tenant no definen si un modulo existe en runtime; solo configuran el uso permitido para ese tenant.
