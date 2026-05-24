# IPRL/CAE Hub

Monorepo inicial para un hub propio de PRL/CAE con backend FastAPI, frontend Next.js TypeScript, PostgreSQL, Redis, Alembic y pytest.

PostgreSQL, Redis, backend y frontend se ejecutan como servicios independientes del servidor, sin contenedores.

## Estructura

```text
backend/              API FastAPI, Alembic, tests y conectores permitidos
config/               Configuracion runtime versionada sin secretos
frontend/             Dashboard Next.js TypeScript
infra/systemd/        Unidades systemd de ejemplo para servidor Linux
docs/                 Especificacion, investigacion y estado de continuidad
specs/                Contratos y manifiestos de referencia
tasks/                Backlog inicial
templates/            Plantillas de investigacion y autorizacion
```

## Version MVP incluida

- Multi-tenant basico con JWT local; `X-Tenant-ID` solo acompana al token y no autentica por si mismo.
- Multi-empresa dentro del tenant: filtros por empresa, resumen por empresa y contexto de empresa en UI.
- Gestion de usuarios con acceso a multiples empresas mediante sesion JWT y tabla `user_company_access`.
- Login real con JWT local. La pantalla local de acceso queda en modo operativo sin alta SaaS visible; los endpoints de signup/verificacion se conservan para pruebas controladas.
- ACL granular por usuario con grants `allow/deny` por tenant, empresa, cuenta de plataforma o sistema.
- Administracion de una plataforma mock por tenant: cuenta de pruebas y usuarios autorizados para validar el flujo.
- Administracion de sistema separada: modulos de plataforma instalados, implementacion disponible y health tecnico.
- Single Sign-On con Google Workspace/OIDC por tenant, PKCE, `state`, `nonce`, dominios permitidos y secretos solo por entorno.
- Capa comercial SaaS: planes, gestorias/revendedores y perfiles comerciales por tenant.
- Multi-idioma inicial ES/EN en la experiencia principal del dashboard, con diccionarios extensibles.
- CRUD inicial de tenants, empresas, centros, trabajadores, cursos PRL, asignaciones a obras, plataformas del trabajador, tipos documentales, documentos y versiones.
- Gestion de trabajadores por alta manual, edicion, baja/restauracion auditada, carga masiva CSV, propuestas desde intake documental y framework ERP local de demo preparado para futuras APIs autorizadas.
- Subida real de ficheros documentales desde UI y API, almacenamiento local, versionado inmutable, apertura/descarga con control de tenant, hash SHA-256 en streaming y limite de tamaño.
- Buzon OCR de carga automatica: dropzone, alcance auto/empresa/trabajador/varios trabajadores, propuesta de tipo documental, fechas y confianza, siempre con revision humana.
- Modelo SQLAlchemy y migracion Alembic para las entidades principales de `docs/03_data_model.md`.
- Catalogo tecnico con plataforma mock local y plataformas comerciales investigadas conservado como referencia backend/documental; la web operativa ya no lo expone y concentra el trabajo en autorizaciones ARM y pasarela RPA.
- Motor inicial de reglas CAE: plantillas por obra/cliente con documentos exigidos y comprobacion por empresa o trabajador.
- Panel de transferencias con jobs, intentos, estado externo normalizado e idempotencia.
- Mapeo estructural de plataformas: snapshots redaccionados, etiquetas estandar, revision humana y comparacion de campos/documentos equivalentes entre plataformas.
- Catalogo de traduccion de plataformas: alias canonicos y mapa de accesos, campos, botones, cabeceras, columnas y estados desde capturas redaccionadas y manifiestos contractuales.
- Catalogo operativo de plataformas: matriz de readiness por operacion, soporte captcha/MFA asistido y prueba de escritura live validada en cuenta dummy autorizada de 6conecta.
- Catalogo de metodos de edicion: por cada contexto plataforma+empresa y cada campo canonico, declara metodo, estado, evidencia, preview requerido, autorizacion y auditoria antes/despues.
- Informe de datos obtenidos y correspondencias: PDF/HTML/CSV por plataforma con capturas redaccionadas, etiquetas visibles y campo externo -> campo interno.
- Conectores RPA de escritura protegida para las plataformas activas ARM actuales: e-coordina, 6conecta, CTAIMA, Nomio, Timenet, Validate, Vitaly CAE, Dokyfy, eGestiona, Folyo, IEDOCE, Integra ASEM, Koordinatu, Metacontratas, Quioo, SGS Gestiona, SmartOSH y UCAE. Preparan jobs en dry-run; 6conecta tiene `upsert_worker` live confirmado con lectura posterior y el resto bloquea ejecucion externa hasta helper live especifico, mapeo aprobado completo y lectura posterior.
- Exchange de escritura por cuenta externa: `GET /api/v1/exchange/write-matrix` resume readiness global, `GET /api/v1/exchange/live-adapters` enumera helper live por plataforma, `GET /api/v1/exchange/write-paths` lista paths de escritura revisables, `POST /api/v1/exchange/{account_proposal_id}/write-paths` guarda paths observados por cuenta/operacion, `POST /api/v1/exchange/write-paths/{path_id}/review` aprueba o rechaza paths con evidencia, `POST /api/v1/exchange/workers/bulk-submit` prepara el alta de un trabajador en todas las cuentas con conector, `POST /api/v1/exchange/{account_proposal_id}/preview` calcula operacion/campos/bloqueos sin escribir fuera, `POST /api/v1/exchange/{account_proposal_id}/submit` resuelve plataforma/conector desde la cuenta y delega en transferencias auditadas, y `POST /api/v1/exchange/{account_proposal_id}/capture-write-screen` abre una peticion segura de mapeo editable en pasarela humana.
- Ingesta de contratos RPA ARM prioritarios como propuestas deshabilitadas: manifiestos, cuentas saneadas y mapeos revisables.
- Centro de plataformas ARM: pantalla operativa por combinacion plataforma + empresa + centro, activacion/desactivacion por contexto, conexion asistida de plataformas autorizadas y control de revision para no generar incidencias en contextos desactivados.
- Conectores RPA ARM: todas las cuentas activas del Excel vigente quedan cubiertas por conector de escritura protegida o por helper live especifico. Todas las escrituras externas siguen el mismo contrato: preview, aprobacion humana, lectura previa anti-duplicado, submit autorizado y lectura posterior; sin helper live especifico devuelven `blocked_live_adapter_missing`.
- Visibilidad de estados documentales externos: APIs sobre `external_document_statuses` y resumen operativo en `/notifications`, con evidencia e-coordina resumida y redaccionada cuando hay lectura autorizada; el mapeo read-only confirmado llega a `documentacion_estado`.
- Auditoria append-only en operaciones de creacion documental, requisitos y transferencias.
- ARM queda separado de la operativa de plataformas: `/arm` mantiene ficha de empresa, trabajadores y documentos propios; `/platforms`, `/assign-worker`, `/notifications` y `/rpa-gateway` concentran la operativa externa.
- Frontend con navegacion global persistente y vistas vigentes: ARM, Plataformas, Anadir trabajador, Notificaciones y Pasarela RPA. Las rutas antiguas de dashboard, autorizaciones, trabajadores, documentos, OCR, reglas, transferencias, auditoria, administracion y sistema se retiraron del frontend.

## Backend

Rutas principales:

- `GET /api/v1/health`: healthcheck de aplicacion con PostgreSQL y Redis configurados.
- `POST /api/v1/tenants`
- `GET /api/v1/saas/overview`
- `GET|POST /api/v1/saas/plans`
- `GET|POST /api/v1/saas/resellers`
- `GET|POST /api/v1/saas/tenant-profiles`
- `GET /api/v1/saas/resellers/{reseller_id}/tenant-profiles`
- `GET|POST /api/v1/users`
- `GET|POST /api/v1/users/roles`
- `POST /api/v1/users/{user_id}/company-access`
- `GET /api/v1/users/{user_id}/company-access`
- `GET /api/v1/users/{user_id}/companies`
- `DELETE /api/v1/users/{user_id}/company-access/{company_id}`
- `GET|POST /api/v1/users/{user_id}/permission-grants`
- `DELETE /api/v1/users/{user_id}/permission-grants/{grant_id}`
- `GET /api/v1/users/{user_id}/effective-permissions`
- `POST /api/v1/auth/signup`
- `POST /api/v1/auth/verify-email`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/companies/onboarding`
- `POST /api/v1/auth/google/signup/start`
- `POST /api/v1/auth/google/signup/callback`
- `GET /api/v1/auth/sso/providers`
- `POST /api/v1/auth/sso/providers/google`
- `POST /api/v1/auth/sso/google/start`
- `POST /api/v1/auth/sso/google/callback`
- `GET /api/v1/auth/sso/me`
- `POST /api/v1/companies`
- `PUT /api/v1/companies/{company_id}`
- `POST /api/v1/workers`
- `PUT /api/v1/workers/{worker_id}`
- `DELETE /api/v1/workers/{worker_id}`
- `POST /api/v1/workers/{worker_id}/restore`
- `POST /api/v1/workers/bulk-upload`
- `GET /api/v1/workers/intake-proposals?company_id={id}`
- `POST /api/v1/workers/import-from-intake`
- `POST /api/v1/workers/import-from-erp`
- `GET /api/v1/tenant-platforms/erp-connectors`
- `GET|POST /api/v1/workers/{worker_id}/trainings`
- `PUT|DELETE /api/v1/workers/{worker_id}/trainings/{training_id}`
- `GET|POST /api/v1/workers/{worker_id}/work-assignments`
- `PUT|DELETE /api/v1/workers/{worker_id}/work-assignments/{assignment_id}`
- `GET|POST /api/v1/workers/{worker_id}/platform-registrations`
- `PUT|DELETE /api/v1/workers/{worker_id}/platform-registrations/{registration_id}`
- `POST /api/v1/document-types`
- `POST /api/v1/documents`
- `POST /api/v1/documents/{document_id}/versions`
- `POST /api/v1/documents/{document_id}/upload`
- `GET /api/v1/documents/{document_id}/versions/{version_id}/download`
- `GET /api/v1/document-intake`
- `POST /api/v1/document-intake/upload`
- `POST /api/v1/document-intake/bulk-upload`
- `GET /api/v1/document-intake/{intake_id}`
- `POST /api/v1/document-intake/{intake_id}/approve`
- `POST /api/v1/requirements/profiles`
- `POST /api/v1/requirements/profiles/{profile_id}/requirements`
- `GET /api/v1/requirements/profiles/{profile_id}/compliance/{entity_type}/{entity_id}`
- `GET /api/v1/platforms/catalog`: catalogo tecnico global de plataformas para backend/documentacion, no visible en la navegacion diaria.
- `GET /api/v1/system/platform-modules`: modulos tecnicos del sistema y health.
- `GET /api/v1/tenant-platforms/access`: cuentas de plataforma y usuarios asignados por tenant.
- `GET|POST /api/v1/tenant-platforms/accounts`
- `GET|POST /api/v1/tenant-platforms/accounts/{account_id}/user-access`
- `DELETE /api/v1/tenant-platforms/accounts/{account_id}/user-access/{user_id}`
- `GET /api/v1/platform-maps/standard-labels`
- `GET|POST /api/v1/platform-maps/snapshots`
- `GET /api/v1/platform-maps/labels`
- `PATCH /api/v1/platform-maps/labels/{label_id}`
- `GET /api/v1/platform-maps/compare`
- `GET /api/v1/platform-maps/data-coverage`
- `GET /api/v1/platform-maps/edit-methods`
- `GET /api/v1/platform-observations/summary`
- `GET /api/v1/platform-observations/entities`
- `GET /api/v1/platform-observations/document-requests`
- `GET /api/v1/platform-observations/operational-map`
- `POST /api/v1/exchange/mass-update/plan`
- `POST /api/v1/exchange/mass-update/submit`
- `GET /api/v1/exchange/write-matrix`
- `GET /api/v1/exchange/live-adapters`
- `GET /api/v1/exchange/write-paths`
- `POST /api/v1/exchange/{account_proposal_id}/write-paths`
- `POST /api/v1/exchange/write-paths/{path_id}/review`
- `POST /api/v1/exchange/capture-write-screens/bulk`
- `POST /api/v1/exchange/workers/bulk-submit`
- `POST /api/v1/exchange/{account_proposal_id}/preview`
- `POST /api/v1/exchange/{account_proposal_id}/submit`
- `POST /api/v1/exchange/{account_proposal_id}/capture-write-screen`
- `POST /api/v1/platform-contracts/import/arm-first-priority`
- `GET /api/v1/platform-contracts/summary`
- `GET /api/v1/platform-contracts/priority-slugs`
- `GET /api/v1/platform-contracts/manifests`
- `GET /api/v1/platform-contracts/accounts`
- `GET /api/v1/platform-contracts/mappings`
- `PATCH /api/v1/platform-contracts/mappings/{mapping_id}`
- `GET /api/v1/platform-authorizations/dashboard`
- `GET /api/v1/platform-authorizations/external-statuses`
- `GET /api/v1/platform-review-schedules`
- `POST /api/v1/platform-review-schedules/ensure`
- `POST /api/v1/platform-review-schedules/activate-12h`
- `GET /api/v1/platform-review-schedules/health`
- `PATCH /api/v1/platform-review-schedules/{schedule_id}`
- `POST /api/v1/platform-review-schedules/{schedule_id}/run-now`
- `GET /api/v1/platform-review-schedules/{schedule_id}/runs`
- `GET /api/v1/platform-review-schedules/rpa-variant-plan`
- `GET /api/v1/rpa-gateway/options`
- `POST /api/v1/rpa-gateway/requests`
- `GET /api/v1/rpa-gateway/requests`
- `POST /api/v1/rpa-gateway/requests/{run_id}/decision`
- `POST /api/v1/rpa-gateway/requests/{run_id}/launch-visible-browser`
- `GET /api/v1/rpa-gateway/requests/{run_id}/browser-status`
- `POST /api/v1/rpa-gateway/requests/{run_id}/sync-readonly-capture`
- `POST /api/v1/transfers`
- `POST /api/v1/transfers/manual-export.zip`
- `GET /api/v1/audit`
- `GET /api/v1/dashboard/summary`
- `GET /api/v1/dashboard/summary?company_id={id}`
- `GET /api/v1/dashboard/companies`

Conectores implementados en esta fase:

- `connector_demo`: simulador local.
- `connector_manual_export`: genera plan/ZIP de exportacion manual sin escribir en plataformas externas.
- `connector_rpa_e_coordina_readonly`: lectura e-coordina protegida por flags, credenciales por entorno y solo en modo lectura/auditoria.
- `connector_rpa_seisconecta_readonly`, `connector_rpa_ctaima_readonly`, `connector_rpa_nomio_readonly`, `connector_rpa_timenet_readonly`, `connector_rpa_validate_readonly`, `connector_rpa_vitaly_cae_readonly`: conectores ARM de lectura segura al mismo nivel operativo base que e-coordina, sin inventar endpoints privados ni persistir filas hasta que haya mapeo aprobado.
- Pasarela RPA visible: `scripts/assisted_platform_browser.py` abre navegador normal con perfil local persistente por tenant/plataforma/cuenta en `storage/rpa-browser-profiles/`; permite que el operador resuelva captcha/MFA una vez y que la siguiente apertura reutilice la sesion sin exportar cookies/tokens a logs, JSON de estado ni evidencias. Si aparece un selector de empresa/cuenta, selecciona automaticamente el contexto objetivo solo cuando hay una coincidencia unica visible; si no, pide validacion humana.

No hay endpoints privados inventados. Los conectores RPA comerciales usan formularios/rutas observadas en capturas redaccionadas o entrada autorizada y quedan bloqueados por configuracion salvo activacion explicita. Las escrituras externas se implementan por operacion y plataforma con preview, mapeo aprobado, aprobacion humana y auditoria.

Para proveedores sin API propia pero con contrato tecnico de automatizacion, el camino de construccion queda documentado en:

- `docs/13_rpa_exchange_api_blueprint.md`: API interna de intercambio y jobs RPA autorizados.
- `docs/14_external_platform_data_scope.md`: alcance por tenant/empresa/datos autorizados.
- `docs/15_provider_contract_intake.md`: como convertir contratos tecnicos en manifiestos implementables.
- `docs/16_platform_structure_mapping_system.md`: sistema para mapear estructuras web redaccionadas, normalizar etiquetas y comparar plataformas.
- `docs/17_provider_contracts_review.md`: revision del paquete de contratos en `requisitos/`.
- `docs/18_arm_first_priority_contract_development.md`: import inicial de las primeras plataformas ARM como propuestas deshabilitadas.
- `docs/19_arm_authorization_dashboard.md`: panel local de autorizaciones ARM, controlador de frecuencia, semaforo e incidencias accionables.
- `docs/20_e_coordina_direct_readonly_pilot.md`: piloto directo e-coordina solo lectura con login confirmado y conector backend.
- `docs/21_external_status_visibility.md`: API/UI para estados documentales externos persistidos y evidencia e-coordina redaccionada.
- `docs/22_e_coordina_status_mapping.md`: mapeo read-only de e-coordina `Documentacion -> Solicitudes de documentacion` y conteo real de estados agregados.
- `docs/23_platform_translation_catalog.md`: catalogo de traduccion entre etiquetas externas, accesos visibles, cabeceras y claves canonicas internas.
- `docs/24_platform_operation_catalog.md`: catalogo operativo por plataforma/operacion, captcha asistido y prueba reversible de escritura no ejecutada.
- `templates/provider_contract_summary_template.md`: resumen versionado sin secretos.
- `templates/rpa_connector_manifest_template.yaml`: manifiesto de operaciones RPA.
- `templates/rpa_field_mapping_template.yaml`: mapeo de campos y tipos documentales.
- `templates/rpa_provider_build_sheet_template.md`: hoja de construccion por proveedor.

## Configuracion central

El fichero `config/iprl-cae.config.toml` centraliza la configuracion no secreta de servidor del producto:

- SSO/OIDC: proveedor Google, dominios permitidos, redirect, TTL de `state` y tokens.
- Autenticacion local: login, signup, verificacion de email y politica minima.
- Email: proveedor y nombres de variables de entorno SMTP.
- OCR: Tesseract, revision humana y limites.
- Conectores: demo, exportacion manual, ERP, API comercial y RPA.
- Jobs, retencion, feature flags y almacenamiento documental.

No debe contener secretos reales. Los secretos se configuran por entorno: `IPRL_CAE_SECRET_KEY`, `IPRL_CAE_GOOGLE_OIDC_CLIENT_SECRET`, credenciales SMTP y futuras credenciales de plataformas.
Por seguridad, los tokens de verificacion expuestos para desarrollo y la autenticacion por cabeceras confiadas vienen desactivados en la configuracion versionada. Los redirects SSO se aceptan solo si el host esta en `sso.allowed_redirect_hosts`.
El backend rechaza el arranque fuera de `local/test` si detecta `secret_key` o `database_url` de ejemplo, SQLite, tokens dev o cabeceras confiadas.

Ficheros de referencia:

- `config/iprl-cae.config.toml`: ejemplo seguro de servidor, con placeholders obligatorios.
- `config/iprl-cae.server.example.toml`: plantilla comentada para instalacion de servidor.
- `config/iprl-cae.local.example.toml`: demo local con SQLite y tokens dev activados solo para entorno local.

En servidor se recomienda copiarlo a `/etc/iprl-cae-hub/config.toml` y definir:

```bash
IPRL_CAE_CONFIG_FILE=/etc/iprl-cae-hub/config.toml
```

Prioridad de configuracion: valores de test/constructor, variables `IPRL_CAE_*`, `.env`, TOML y defaults de codigo. Por tanto, el fichero TOML sirve como base operativa y el entorno sigue mandando en despliegue.

## OCR documental

El OCR documental funciona como buzon de propuestas:

- Extrae texto directo de TXT/CSV/PDF con capa de texto.
- Usa Tesseract para imagenes si el binario esta instalado en el servidor. El backend admite `TESSERACT_CMD` y tambien busca rutas habituales de Windows con `tessdata` valido.
- Clasifica contra el catalogo documental CAE.
- Busca empresa por CIF/nombre y trabajador por nombre y ultimos 4 del identificador.
- Permite orientar la carga como `auto`, `company`, `single_worker` o `multiple_workers`.
- Admite carga ZIP por lotes con `POST /api/v1/document-intake/bulk-upload`, incluyendo ZIP anidados limitados, rutas seguras y extensiones documentales controladas.
- Detecta fechas de emision/caducidad con heuristicas conservadoras.
- Guarda solo extracto redaccionado y señales estructuradas, no el OCR completo.
- Crea `Document`/`DocumentVersion` solo tras `approve`.

Sin vista frontend vigente; las evidencias pendientes se resumen en `/notifications` y la aprobacion/documentacion final se trabaja desde `/arm`.

Skill Codex local creada: `iprl-cae-ocr-intake` en `C:\Users\ikerh\.codex\skills\iprl-cae-ocr-intake`.

## Google SSO

El modulo Google SSO usa OpenID Connect oficial de Google, no es un conector CAE. Se soportan dos flujos:

- Signup SaaS con Google: `POST /api/v1/auth/google/signup/start` y callback `POST /api/v1/auth/google/signup/callback`.
- SSO por tenant ya creado: `POST /api/v1/auth/sso/google/start` y callback `POST /api/v1/auth/sso/google/callback`.

Para activarlo:

1. Crear credenciales OAuth 2.0 en Google Cloud con redirect URI de la app.
2. Configurar en el servidor:

```bash
IPRL_CAE_GOOGLE_OIDC_CLIENT_ID=...
IPRL_CAE_GOOGLE_OIDC_CLIENT_SECRET=...
IPRL_CAE_SECRET_KEY=valor-largo-aleatorio
```

3. Activar el proveedor:

```bash
curl -X POST http://localhost:8000/api/v1/auth/sso/providers/google \
  -H "X-Tenant-ID: 1" \
  -H "Content-Type: application/json" \
  -d '{"status":"active","allowed_domains":["empresa.com"],"auto_provision":false}'
```

El secreto no se devuelve por API ni se guarda en el repositorio. El callback valida firma, audiencia, issuer, `nonce` y dominio alojado antes de emitir un token local del backend.
La verificacion se ha contrastado con la documentacion oficial de Google OpenID Connect: https://developers.google.com/identity/openid-connect/openid-connect

## Catalogo de plataformas

El proyecto queda sin conectores comerciales activos. Existe una plataforma local de prueba y un catalogo de plataformas comerciales investigadas:

- `mock_cae`: plataforma mock para validar datos, permisos, usuarios, mapeos y exportaciones sin sistema externo.
- Comerciales catalogadas: Dokify, Nalanda, Konvergia, CTAIMA/Twind, 6conecta, Metacontratas, e-coordina, EcoGestor, eGestiona, UCAE, SG Red, Sicondoc/Construred, Validate, tdoc, Obralia/Nalanda construccion, CoordinaPlus y Quioo.

El dossier de API/fuentes esta en `docs/09_platform_api_research.md`. La investigacion queda conservada en backend desde `GET /api/v1/platforms/catalog` bajo el bloque `technical_research`, pero no se muestra en la interfaz diaria. La ruta `/platforms` es el centro operativo de contextos plataforma + empresa + centro.

Cada plataforma puede declarar varios metodos de conexion o trabajo:

- `manual_export`: disponible mediante `connector_manual_export`.
- `api_official`: deshabilitado hasta tener documentacion oficial o autorizacion contractual.
- `authorized_rpa`: deshabilitado hasta tener autorizacion explicita, manifiesto, preflight y aprobacion humana.

No se catalogan nombres comerciales reales en la aplicacion hasta tener una necesidad y autorizacion concreta.

La administracion queda separada en dos planos:

- Empresa/tenant: cuentas de plataforma, usuarios asignados, permisos, modo `send/receive` y operaciones permitidas.
- Sistema: modulos instalados, conectores implementados o deshabilitados y health tecnico.

La plataforma mock funciona en `dry_run` y con aprobacion manual.

## Requisitos locales

- Python 3.11 o superior.
- Node.js 20 o superior para el frontend.
- PostgreSQL 14 o superior como servicio del servidor.
- Redis 7 o superior como servicio del servidor.
- GNU Make opcional; los comandos se pueden ejecutar manualmente.

## Instalacion backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp ../.env.example .env
```

Configura `IPRL_CAE_DATABASE_URL` e `IPRL_CAE_REDIS_URL` apuntando a los servicios reales del servidor.
Configura tambien `IPRL_CAE_DOCUMENT_STORAGE_PATH` para el repositorio local de documentos y `IPRL_CAE_MAX_UPLOAD_BYTES` para el limite por fichero.

Crear base de datos de ejemplo en PostgreSQL:

```sql
CREATE USER iprl_cae WITH PASSWORD 'change-me';
CREATE DATABASE iprl_cae OWNER iprl_cae;
```

Aplicar migraciones y seed:

```bash
cd backend
alembic upgrade head
python -m app.db.seed
```

Arrancar backend:

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Instalacion frontend

```bash
cd frontend
npm install
npm run dev
```

Aplicacion: `http://localhost:3000`.

Vistas disponibles:

- `/`
- `/login`
- `/verify-email`
- `/auth/google/callback`
- `/onboarding/company`
- `/select-company`
- `/arm`
- `/platforms`
- `/assign-worker`
- `/notifications`
- `/rpa-gateway`

La navegacion principal esta agrupada en `ARM` y `Operativa`. Login, seleccion de empresa, verificacion, Google callback y onboarding mantienen una pantalla limpia sin shell operativo.
La vista `/arm` mantiene los datos propios de ARM: ficha empresa, listado de trabajadores, detalle editable de cada trabajador, documentos normalizados, ultima subida, descarga y subida de nuevas versiones.
La vista `/platforms` muestra contextos de plataforma por plataforma + empresa + centro, filtros por plataforma/empresa/centro, activacion/desactivacion, estado de preview de escritura y conexion asistida de plataformas autorizadas. Consume el mapa `/platform-observations/operational-map` para mostrar lectura, superficies, helper live, paths de escritura y si el contexto esta mapeado read/write.
La vista `/assign-worker` permite seleccionar o arrastrar trabajadores ARM hacia una o varias plataformas activas y prepara jobs auditados de alta/documentacion.
La vista `/notifications` resume solo plataformas activas, evidencias pendientes de validacion, incidencias, warnings y acciones de revision. Tambien muestra el plan de `Actualizacion masiva` para preparar desde el Hub altas/documentos pendientes, crear jobs dry-run y abrir pasarelas cuando falte mapeo/helper.
La vista `/rpa-gateway` muestra la pasarela humana para RPA asistida: es una pantalla propia del Hub, distinta de la web original, donde el operador selecciona o recibe una plataforma, genera el flujo guiado, autoriza entrada en navegador visible, usa credenciales ya configuradas sin volver a pedirlas, resuelve captcha/MFA/aviso si aparece y ve el estado del navegador (`waiting_for_login_form`, `human_control_required`, `credentials_submitted`, `browser_open_for_operator`). El lanzador usa Chromium de Playwright y, si no esta instalado, prueba Chrome o Microsoft Edge del sistema. Cuando la plataforma permite entrar en modo lectura, el helper recoge una captura tecnica redaccionada (titulos, formularios, botones, cabeceras, contadores y senales objetivo, sin cookies, tokens, HTML, HAR, capturas ni valores de fila) y permite `Sincronizar lectura con Hub`. Las acciones de escritura externa (`upsert_worker`, `upload_worker_document`, etc.) deben ejecutarse en jobs separados con preview, mapeo aprobado, aprobacion humana y auditoria.
La vista `/login` permite entrar con usuario/password y redirige siempre a `/select-company` antes de cualquier pantalla operativa. En la SQLite ARM-only solo aparece `ARM Industrial Assemblies, S.L.` y la seleccion queda guardada como contexto activo antes de pasar a la pasarela RPA. El alta SaaS, la verificacion de email y el signup por Google no se muestran en esta pantalla mientras el foco sea la aplicacion.

Importacion de trabajadores:

- Manual: `POST /api/v1/workers`.
- Edicion: `PUT /api/v1/workers/{worker_id}`.
- Borrado/restauracion logica auditada: `DELETE /api/v1/workers/{worker_id}` y `POST /api/v1/workers/{worker_id}/restore`.
- CSV masivo: `POST /api/v1/workers/bulk-upload` con columnas como `company_id,first_name,last_name,dni,naf,puesto,obra`.
- Intake documental: `GET /api/v1/workers/intake-proposals?company_id={id}` previsualiza nombres detectados en lotes `multiple_workers`; `POST /api/v1/workers/import-from-intake` crea fichas minimas con `dry_run=true` por defecto, auditoria y sin inventar DNI/NAF.
- ERP: no se expone configuracion ERP en el frontend operativo actual; el backend conserva el conector local `erp_demo_csv` para previsualizar/aprobar importaciones sin sistemas externos.
  En servidor, la importacion ERP requiere `features.worker_erp_import=true` en configuracion local/tenant controlada; por defecto queda apagada en la plantilla de servidor.

## Arranque rapido de producto local

En Windows, este repositorio incluye un modo demo sin contenedores que usa:

- Node portable en `.tools/`.
- Backend FastAPI en `http://localhost:8001`.
- Frontend Next real en `http://localhost:3000`.
- SQLite local en `storage/demo.db` para poder probar sin instalar PostgreSQL en esta maquina.
- Acceso mediante login real contra los usuarios demo seedados; el frontend ya no usa identidad demo implicita.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-node-portable.ps1
cd frontend
..\.tools\node-v24.15.0-win-x64\npm.cmd install
cd ..
powershell -ExecutionPolicy Bypass -File scripts\start-product.ps1
```

PostgreSQL sigue siendo el objetivo de servidor/produccion; SQLite es solo para demo local.

Usuario local creado por el seed:

- `demo` / `demo`: acceso rapido al trabajo operativo ARM, redirigido primero a `/select-company`.

El seed local no crea empresas, trabajadores, usuarios ni planes SaaS de muestra. El entorno visible queda limitado a `ARM Industrial Assemblies, S.L.`, trabajadores ARM creados desde intake documental y propuestas documentales ARM pendientes de revision.

Para limpiar una SQLite antigua y dejarla en modo ARM-only:

```powershell
python scripts\clean_local_arm_only.py
```

Runner local de revisiones vencidas:

```powershell
python scripts\run_due_platform_reviews.py --tenant-id 1 --list-only
python scripts\run_due_platform_reviews.py --tenant-id 1
```

El runner usa los mismos bloqueos que la API: sin flags RPA y credenciales por entorno registra el run como bloqueado y no accede a terceros.

Smoke local de pasarela humana con pagina demo de captcha/MFA, sin acceder a terceros:

```powershell
python scripts\smoke_rpa_gateway_captcha_demo.py
```

El resultado esperado es deteccion de captcha/MFA, peticion en `human_action_required`,
decision humana registrada y `changes_applied=0`.

Catalogo de traduccion y mapas de plataformas desde capturas redaccionadas:

```powershell
python scripts\import_arm_platform_maps.py --replace
python scripts\build_platform_translation_catalog.py
python scripts\build_platform_operation_catalog.py
python scripts\build_platform_field_edit_methods.py --tenant-id 1 --priority-group all
python scripts\build_platform_obtained_data_mapping_report.py --tenant-id 1
python scripts\probe_platform_write_previews.py --connector-dry-run
```

## Comandos

```bash
make dev        # backend en desarrollo
make test       # backend pytest + frontend vitest
make lint
make typecheck
make migrate
make seed
make e2e
```

Si `make` no esta instalado, ejecuta el comando equivalente dentro de `backend/` o `frontend/`.

## Despliegue sin contenedores

1. Crear usuario de sistema `iprlcae`.
2. Copiar el proyecto a `/opt/iprl-cae-hub`.
3. Copiar `config/iprl-cae.config.toml` a `/etc/iprl-cae-hub/config.toml` y ajustar configuracion no secreta.
4. Crear `/etc/iprl-cae-hub/backend.env` a partir de `.env.example` con secretos reales e `IPRL_CAE_CONFIG_FILE=/etc/iprl-cae-hub/config.toml`.
5. Instalar dependencias Python en `/opt/iprl-cae-hub/backend/.venv`.
6. Instalar dependencias y construir frontend con `npm install && npm run build`.
7. Copiar las unidades de `infra/systemd/` a `/etc/systemd/system/`.
8. Ejecutar:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now iprl-cae-backend
sudo systemctl enable --now iprl-cae-frontend
```

## Tests

Backend:

```bash
cd backend
python -m pytest
```

Frontend:

```bash
cd frontend
npm test
```

En esta entrega se ha seguido el requisito del prompt actual: despliegue como servicios independientes del servidor, sin contenedores.

Resultados verificados en esta iteracion:

- `python -m pytest backend\tests -q`: 63 passed.
- `python -m ruff check backend\app backend\tests scripts`: OK.
- `python -m alembic heads`: `0016_platform_write_paths (head)`.
- `npm run typecheck` en `frontend` usando `.tools\node-v24.15.0-win-x64`: OK.
- `npm test` en `frontend`: 1 archivo, 7 tests passed.
- `npm run e2e` en `frontend` contra producto local levantado: 1 Playwright test passed.
- Smoke local ARM-only: `http://127.0.0.1:8001/api/v1/health`, `http://127.0.0.1:3000/login`, acceso `demo/demo`, 1 empresa ARM, 7 trabajadores ARM, 39 intakes ARM, 0 planes SaaS, 0 cuentas mock y 0 runs de pasarela de prueba.
- Smoke platform maps: 52 etiquetas estandar, 35 snapshots ARM y comparacion `worker.full_name` con 3 plataformas agrupadas.
- Smoke catalogo traduccion: 49 plataformas en catalogo, 22 con capturas redaccionadas, 1.428 alias, 1.714 accesos/campos/cabeceras y auditoria `rg` sin patrones de secretos.
- Smoke catalogo operativo: 53 plataformas, 423 entradas de operacion, 282 escrituras plan-only, 0 escrituras externas verificadas y 47 plataformas con captcha/MFA asistido o control humano.
- Smoke platform contracts: 6 manifiestos ARM prioritarios, 11 cuentas deshabilitadas y 306 mapeos pendientes.
- Smoke authorizations: panel ARM devuelve 6 plataformas prioritarias, 7 trabajadores ARM, 6 schedules de revision y 48 incidencias locales para corregir en Hub; la API de estados externos lista estados persistidos por version documental cuando existen.
- Smoke runner schedules: `python scripts\run_due_platform_reviews.py --tenant-id 1 --list-only` ejecuta y lista schedules vencidos sin acceder a terceros.
- Smoke directo e-coordina: captura ARM/ARITEX y conector backend confirman `login_likely_success`, sin captcha/MFA y con contexto `ARITEX`.
