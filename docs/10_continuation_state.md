# 10 - Estado de continuidad del proyecto

Fecha del checkpoint: 2026-05-20.

Este documento guarda el estado operativo del proyecto para poder retomarlo en otra sesion sin depender del historial del chat.

## Reglas que siguen vigentes

- El prompt actual manda si contradice decisiones anteriores.
- Antes de escribir codigo: leer `AGENTS.md` y todos los documentos de `docs/`.
- No usar Docker ni contenedores. El producto debe poder ejecutarse como servicios independientes en servidor.
- No implementar conectores reales de plataformas comerciales sin documentacion oficial, contrato/autorizacion y secretos fuera del repositorio.
- No inventar endpoints, selectores RPA, credenciales ni bypass de controles.
- Todo conector externo debe operar con `dry_run`, aprobacion manual y auditoria antes/despues de acciones externas.
- Mantener separadas tres capas: sistema, tenant/empresa y operativa CAE.
- Ejecutar pruebas antes de declarar una iteracion terminada.

## Estado funcional actual

Stack:

- Backend FastAPI en `backend/`.
- Frontend Next.js TypeScript en `frontend/`.
- PostgreSQL y Redis como objetivo de servidor.
- SQLite solo para demo local mediante `scripts/start-product.ps1`.
- Alembic, pytest, Vitest y Playwright configurados.

Producto local:

- Arranque: `powershell -ExecutionPolicy Bypass -File scripts\start-product.ps1`.
- Frontend: `http://127.0.0.1:3000`.
- Backend: `http://127.0.0.1:8001`.
- API docs: `http://127.0.0.1:8001/api/v1/docs`.
- Health: `http://127.0.0.1:8001/api/v1/health`.

Usuario local:

- `demo` / `demo`: acceso rapido para trabajo operativo ARM, redirigido primero a `/select-company`.
- La SQLite local queda en modo ARM-only: 1 tenant ARM, 1 empresa ARM, 7 trabajadores ARM y 39 propuestas documentales ARM. No se seedan empresas, trabajadores, usuarios, planes SaaS ni cuentas mock de muestra.

## Modulos implementados

- Login local con JWT. La UI local de `/login` esta en modo acceso operativo y no muestra alta SaaS.
- Selector de empresa obligatorio: el `AppShell` redirige a `/select-company` si no hay empresa confirmada; en ARM-only solo se puede confirmar `Empresa Demo Industrial, S.L.`.
- Signup con email/password y verificacion de email conservados como endpoints backend para pruebas controladas.
- Signup/SSO Google OIDC preparado con PKCE, `state`, `nonce`, dominios permitidos y secretos por entorno.
- Onboarding de empresa tras alta.
- Multi-tenant y multiempresa.
- Usuarios con acceso a multiples empresas.
- RBAC granular por rol, tenant, empresa, sistema y grants `allow/deny`.
- SaaS/reseller: endpoints conservados, pero la UI local de trabajo y el seed ARM-only no crean planes ni revendedores de muestra.
- Navegacion global agrupada en ARM y Operativa.
- ARM: `/arm` contiene ficha de empresa, listado de trabajadores, detalle editable de cada trabajador, documentos normalizados, ultima subida, descarga y carga de nuevas versiones.
- Operativa de plataformas: `/platforms` gestiona contextos plataforma + empresa + centro, filtros, activacion/desactivacion y conexion asistida de plataformas autorizadas.
- Alta en plataformas: `/assign-worker` permite seleccionar o arrastrar trabajadores ARM hacia plataformas activas y preparar jobs auditados.
- Notificaciones: `/notifications` consolida incidencias, warnings, evidencias pendientes y acciones solo de plataformas activas.
- OCR intake y reglas CAE se conservan como API/backend, pero sus pantallas antiguas fueron retiradas del frontend operativo nuevo.
- Reglas CAE: perfiles, requisitos y calculo de cumplimiento por empresa o trabajador.
- Transferencias: jobs, intentos, exportacion manual ZIP y auditoria.
- Plataforma local `mock_cae` para pruebas unitarias sin terceros; no se crea cuenta visible en la SQLite ARM-only.
- Catalogo tecnico de plataformas investigadas conservado en backend/documentacion con fuentes en `docs/09_platform_api_research.md`; no se expone en la navegacion diaria.
- Mapeo estructural de plataformas: snapshots redaccionados, etiquetas estandar, revision humana y comparacion entre plataformas.
- Pasarela RPA: `/rpa-gateway` conserva el flujo humano asistido, autorizacion previa, navegador visible, credenciales configuradas en servidor, parada ante captcha/MFA/control humano y sincronizacion de capturas de solo lectura.
- Piloto directo e-coordina en solo lectura: login ARM/ARITEX confirmado, conector backend, runs auditables y runner local para schedules vencidos.
- Administracion tenant: usuarios, accesos multiempresa, permisos efectivos, plataformas/cuentas y SaaS.
- Administracion sistema: modulos tecnicos y health.

## Seguridad cerrada en la ultima iteracion

- `X-Tenant-ID` no autentica por si solo; las rutas protegidas requieren bearer token.
- Se eliminaron fallbacks demo implicitos del frontend.
- `/audit`, `/tenants`, `/saas` y rutas de sistema requieren permisos adecuados.
- SSO valida `redirect_uri` y `next_url` contra hosts permitidos.
- Se bloquearon `auth_dev_tokens_enabled` y `trusted_header_auth_enabled` fuera de local/test.
- El backend rechaza arranque no local con SQLite, secretos placeholder o DB con credenciales de ejemplo.
- Documentos y trabajadores usan permisos explicitos `document.read/write` y `worker.read/write`.
- Empresas usan `company.write` para edicion.
- Requisitos usan `requirement.read` donde aplica.

## Configuracion

Ficheros:

- `config/iprl-cae.config.toml`: plantilla versionada de servidor con placeholders y sin secretos reales.
- `config/iprl-cae.local.example.toml`: demo local con SQLite y tokens dev solo para entorno local.
- `config/iprl-cae.server.example.toml`: ejemplo seguro de servidor.
- `scripts/start-product.ps1`: arranque local sin contenedores.

Variables importantes:

- `IPRL_CAE_CONFIG_FILE`.
- `IPRL_CAE_DATABASE_URL`.
- `IPRL_CAE_REDIS_URL`.
- `IPRL_CAE_SECRET_KEY`.
- `IPRL_CAE_GOOGLE_OIDC_CLIENT_ID`.
- `IPRL_CAE_GOOGLE_OIDC_CLIENT_SECRET`.
- `IPRL_CAE_FEATURES__WORKER_ERP_IMPORT`.

## Conectores

Implementados:

- `connector_demo`: simulador local.
- `connector_manual_export`: exportacion manual ZIP.
- `erp_demo_csv`: conector local de demo para previsualizar/aprobar importaciones de trabajadores.
- `erp_authorized_api`: plantilla deshabilitada para APIs autorizadas futuras.
- Mapa estructural previo a conectores: `docs/16_platform_structure_mapping_system.md`, rutas `/api/v1/platform-maps/*` y script `scripts/import_arm_platform_maps.py`.
- Documentos de construccion para RPA autorizada contra formularios sin API propia: `docs/13_rpa_exchange_api_blueprint.md`, `docs/14_external_platform_data_scope.md`, `docs/15_provider_contract_intake.md` y plantillas `templates/rpa_*`.

No implementados:

- APIs reales de Dokify, Nalanda, CTAIMA, Metacontratas, 6conecta, EcoGestor, UCAE, e-coordina, Validate, etc.
- RPA real contra plataformas comerciales salvo:
  - piloto e-coordina de solo lectura, bloqueado por configuracion y sin escrituras;
  - piloto 6conecta `connector_rpa_seisconecta_write` para `upsert_worker` en cuenta dummy autorizada, con aprobacion manual, navegador visible, lectura previa anti-duplicado y lectura posterior obligatoria.

La investigacion tecnica esta guardada en `docs/09_platform_api_research.md` y disponible en backend para referencia, pero ya no se expone como catalogo tecnico. La UI vigente de `/platforms` es el centro operativo de contextos plataforma + empresa + centro.

## Limpieza UI 2026-05-20

Se rehizo el alcance del frontend y se retiraron las pantallas antiguas que ya no forman parte del flujo nuevo:

- Eliminadas: `/admin`, `/audit`, `/authorizations`, `/documents`, `/intake`, `/requirements`, `/system`, `/transfers`, `/workers`.
- Eliminados: `frontend/app/components/DashboardClient.tsx` y `frontend/lib/i18n.ts`, que solo daban servicio al dashboard antiguo.
- Conservadas: `/arm`, `/platforms`, `/assign-worker`, `/notifications`, `/rpa-gateway`, `/login`, `/select-company`, `/verify-email`, `/auth/google/callback` y `/onboarding/company`.
- Limpieza CSS: retirados estilos de dashboard/autorizaciones/workers/OCR/transferencias/admin/sistema que ya no tenian consumidores.
- No se eliminaron endpoints backend de workers, documents, transfers, audit, requirements o intake porque las pantallas nuevas y los jobs siguen usandolos como API operativa.

## Asignacion trabajador-plataforma 2026-05-20

- `/assign-worker` carga `GET /api/v1/workers/{worker_id}/platform-registrations` para cada trabajador visible.
- Cada trabajador muestra resumen de destinos disponibles y altas ya existentes.
- Cada contexto de plataforma muestra estado visual por trabajador seleccionado: `disponible`, `ya existe`, `desactivada` o `sin conector`.
- El boton `Anadir aqui`, drag/drop y `Anadir a todas` filtran destinos ya existentes antes de crear jobs. El backend mantiene el bloqueo final con `409` si alguien intenta repetir el alta.
- Prueba local ejecutada: Bruno Lopez Martin no tenia registro en `mock_cae`; `POST /api/v1/transfers` con `connector_demo` creo el job `#23`, genero registro `Plataforma Mock CAE: accepted` y el segundo intento devolvio `409` por duplicado.
- Prueba sobre plataforma ARM real preparada sin escritura externa: Bruno -> 6conecta/VELARTIA genero job `#24` en `blocked_mapping_review_required`; no se escribio fuera porque faltan mapeos/datos aprobados.
- Prueba live autorizada 6conecta completada: trabajador local `#20 Prueba Hub Confirmada Lectura`, transfer `#33`, estado `confirmed_external`, `valid_external_write=true`, lectura posterior confirmada y registro local `WorkerPlatformRegistration #4` en plataforma/cuenta `#8`.
- Control anti-duplicado externo validado: trabajador local `#18 Prueba Alta Real Confirmable`, transfer `#31`, estado `already_exists_external`; el Hub confirmo por lectura que ya existia en 6conecta y no repitio el alta.
- Incidencia historica: transfer `#32` creo el trabajador externo pero se registro como `submit_not_observed`; despues se corrigio el helper para que, si no observa el submit pero la lectura posterior confirma un trabajador que no existia en la lectura previa, marque `confirmed_external`.

## Pruebas verificadas en este checkpoint

Backend:

```powershell
python -m pytest backend\tests
# 56 passed

python -m ruff check backend\app backend\tests scripts\clean_local_arm_only.py scripts\import_arm_platform_maps.py scripts\import_arm_first_priority_contracts.py scripts\smoke_rpa_gateway_captcha_demo.py scripts\run_due_platform_reviews.py
# All checks passed

cd backend
python -m alembic heads
# 0014_platform_review_runs (head)
```

Frontend:

```powershell
$env:PATH = "D:\PLATAFORMAS\.tools\node-v24.15.0-win-x64;$env:PATH"
npm.cmd run typecheck
# OK

npm.cmd test
# 1 test file, 7 tests passed

npm.cmd run e2e
# 1 Playwright test passed
```

E2E historico:

- Login, creacion/edicion de trabajador y subida documental se validaron antes de pasar la SQLite local a ARM-only.

Smoke local adicional:

- `GET http://127.0.0.1:8001/api/v1/health`: `ok`.
- `POST /api/v1/auth/login` con `demo/demo`: emite sesion para `demo@demo.invalid`.
- `/login`: no muestra alta SaaS; redirige a `/select-company?next=/rpa-gateway` tras login.
- `/select-company`: muestra solo `Empresa Demo Industrial, S.L.` y obliga a confirmar la empresa antes de entrar en `/rpa-gateway`.
- `python scripts\clean_local_arm_only.py`: deja 1 tenant, 1 empresa ARM, 7 trabajadores ARM, 39 intakes ARM, 0 planes SaaS, 0 cuentas mock, 0 runs de pasarela de prueba.
- `GET /api/v1/dashboard/companies`: 1 empresa, `Empresa Demo Industrial, S.L.`.
- `GET /api/v1/workers`: 7 trabajadores ARM.
- `GET /api/v1/rpa-gateway/requests`: 0 ejecuciones de prueba tras la limpieza.
- `GET /api/v1/platform-maps/standard-labels`: 52 etiquetas estandar.
- `GET /api/v1/platform-maps/snapshots`: 35 snapshots ARM disponibles.
- `GET /api/v1/platform-maps/compare?standard_key=worker.full_name`: 3 plataformas agrupadas, 10 etiquetas.
- `GET /api/v1/platform-contracts/summary`: 6 manifiestos, 11 cuentas y 306 mapeos pendientes.
- `GET /api/v1/platform-authorizations/dashboard`: 6 plataformas ARM prioritarias, 7 trabajadores ARM y 48 incidencias locales.
- `POST /api/v1/platform-review-schedules/ensure`: 6 schedules de revision ARM.
- `GET /api/v1/platform-review-schedules/{schedule_id}/runs`: historial de ejecuciones auditables por schedule.
- `python scripts\run_due_platform_reviews.py --tenant-id 1 --list-only`: runner local operativo; en el checkpoint no habia schedules vencidos.
- e-coordina ARM/ARITEX directo: `login_likely_success`, sin captcha/MFA y contexto ARITEX confirmado.

## Archivos clave recientes

- `backend/app/api/workers.py`: CRUD trabajador, restore, subrecursos y ERP framework.
- `backend/app/api/workers.py`: tambien expone `GET /workers/intake-proposals` y `POST /workers/import-from-intake` para crear fichas minimas desde lotes documentales revisables.
- `backend/app/api/documents.py`: permisos de documentos y auditoria de actor.
- `backend/app/api/document_intake.py`: permisos de OCR intake.
- `backend/app/api/document_intake.py`: tambien expone `POST /document-intake/bulk-upload` para cargar ZIP documentales como propuestas pendientes.
- `backend/app/services/access_control.py`: helpers de permiso por empresa.
- `backend/app/services/erp.py`: registro de conectores ERP locales.
- `backend/app/core/config.py`: validacion de seguridad runtime.
- `frontend/app/arm/page.tsx`: ficha ARM de empresa/trabajadores con documentos normalizados, subida, descarga y edicion.
- `frontend/app/platforms/page.tsx`: centro de contextos plataforma + empresa + centro.
- `frontend/app/assign-worker/page.tsx`: preparacion de alta/documentacion de trabajador en plataformas activas.
- `frontend/app/notifications/page.tsx`: visor operativo de incidencias, warnings y evidencias pendientes.
- `frontend/tests/e2e/worker-flow.spec.ts`: flujo e2e real.
- `frontend/playwright.config.ts`: configuracion Playwright.
- `README.md`: instalacion, estado y resultados.
- `AGENTS.md`: reglas y checkpoint.

## Carga ARM 2026-05-18

Se cargaron en la demo local documentos propios de ARM desde `requisitos/`:

- Empresa ARM creada/encontrada como `Empresa Demo Industrial, S.L.` con `company_id=5`.
- `Documentación empresa ARM.zip`: 7 propuestas documentales de empresa, todas en `pending_review`.
- `replataformasycontraseas.zip`: 32 propuestas documentales de trabajadores, todas en `pending_review`.
- El importador de propuestas de trabajadores detecto 7 fichas ARM y las creo sin DNI/NAF: Alicia Gomez, Bruno Lopez, Carlos Perez Ruiz, Daniel Pendiente revisar, Eduardo Pendiente revisar, Fernando Pendiente revisar e Hugo Pendiente revisar.
- Las fichas incompletas quedan marcadas con apellidos `Pendiente revisar` y notas CAE para revision humana antes de aprobar documentos.
- CTAIMA/CLIENTE_A queda registrado como observacion humana ARM: falta `Entrega de EPIs` para Alicia Gomez. La prueba tecnica inicial de acceso del 2026-05-19 a la fila ARM 29 se detuvo antes de login por captcha/control. En la repeticion guiada posterior el operador logro entrar en CTAIMA; los relanzamientos quedaron bloqueados por control de sesion duplicada (`Ya existe una sesion activa`), que debe cerrar o dejar expirar el operador.
- El visor `Pendiente por plataforma y empresa` permite lanzar `Recargar datos` por combinacion plataforma+cuenta externa: crea una peticion en pasarela humana, abre `/rpa-gateway?request={id}` con el flujo guiado enfocado, registra autorizacion antes de lanzar el navegador visible, resuelve credenciales en memoria desde configuracion local/env, muestra estado del navegador mediante `browser-status`, recoge una captura tecnica redaccionada de solo lectura cuando la plataforma permite continuar y habilita `Sincronizar lectura con Hub`. La sincronizacion guarda evidencia `gateway.readonly_capture`, conserva `dry_run`/`manual_approval_required` y mantiene `changes_applied=[]`; la persistencia fila a fila queda bloqueada hasta aprobar mapeos CTAIMA -> Hub.
- La seccion `Estrategia RPA por plataforma` usa `GET /api/v1/platform-review-schedules/rpa-variant-plan?priority_group=all` para cubrir todas las plataformas ARM actuales. Lee el snapshot local ARM y muestra variantes seguras de login/contexto/lectura/mapeo por plataforma. La politica limita cada ejecucion a un envio de credenciales por cuenta y detiene el flujo ante captcha, MFA, aviso legal, sesion duplicada, rate limit, empresa inesperada o pantalla no reconocida.
- Detalle operativo en `docs/12_arm_document_intake.md`.

## Mapeo estructural ARM 2026-05-18

Se importaron las capturas tecnicas redaccionadas de `artifacts/platform-captures/` a la demo local:

- Comando: `python scripts\import_arm_platform_maps.py --replace`.
- Snapshots importados: 35.
- Etiquetas estructurales creadas: 1.292.
- Claves estandar detectadas en catalogo: 48.
- Tablas nuevas: `platform_structure_snapshots` y `platform_discovered_labels`.
- API nueva: `/api/v1/platform-maps/standard-labels`, `/snapshots`, `/labels` y `/compare`.
- Documentacion: `docs/16_platform_structure_mapping_system.md`.
- No se ejecutaron escrituras externas ni se guardaron secretos o cuerpos HTTP.

## Catalogo traduccion plataformas 2026-05-18

Se implemento y ejecuto:

- Script: `scripts/build_platform_translation_catalog.py`.
- Artefactos: `artifacts/platform-translation/`.
- Documento: `docs/23_platform_translation_catalog.md`.
- Capturas procesadas: 35.
- Plataformas en catalogo de traduccion: 49.
- Plataformas con capturas redaccionadas: 22.
- Alias de traduccion: 1.428.
- Accesos/campos/cabeceras detectados: 1.714.
- Etiquetas pendientes sin clave canonica: 1.039.

La taxonomia vive en `backend/app/services/platform_mapping.py` y ahora cubre campos de empresa, trabajador, documento, activos, fechas, estados y accesos. El sistema no guarda valores de filas ni secretos; solo forma de campos, etiquetas, cabeceras, botones y propuestas contractuales.

## Catalogo operativo plataformas 2026-05-18

Se implemento y ejecuto:

- Script: `scripts/build_platform_operation_catalog.py`.
- Artefactos: `artifacts/platform-operations/`.
- Documento: `docs/24_platform_operation_catalog.md`.
- Plataformas catalogadas: 53.
- Entradas de operacion: 423.
- Operaciones de escritura verificadas con guardado externo: 0.
- Operaciones de escritura catalogadas solo como plan/dry-run: 282.
- Plataformas con captcha/MFA asistido o control humano: 47.

Conclusion operativa:

- Captcha/MFA se soporta solo como navegador asistido por humano y estado `human_action_required`; no hay bypass.
- La prueba de cambiar/guardar/restaurar un campo queda definida, pero requiere entidad dummy o sandbox y aprobacion explicita antes de ejecutarse.
- La unica lectura real de estados externos verificada con valores agregados sigue siendo e-coordina `documentacion_estado`.

## Revision contratos proveedores 2026-05-18

Se reviso `requisitos/iker_contratos_plataformas_max_scope_2026-05-18/`:

- Manifiestos RPA: 47.
- Cuentas procesadas: 115.
- Cuentas activas: 91.
- Cuentas ARM: 34, todas activas.
- Plataformas ARM detectadas: 20.
- Plataformas con host/URL pendiente: 16; en ARM afecta a Quironprevencion y Sarenet.
- Todos los manifiestos mantienen `requires_signed_authorization=true`, `dry_run_default=true` y `manual_approval_required=true`.
- Todos los mapeos documentales siguen pendientes de catalogo externo de plataforma.
- Informe: `docs/17_provider_contracts_review.md`.

## Desarrollo contratos RPA ARM prioritarios 2026-05-18

Se implemento la primera capa de configuracion revisable para:

- e-coordina.
- 6conecta.
- Validate.
- Timenet.
- Nomio.
- Vitaly CAE.

Estado:

- Migracion nueva: `backend/alembic/versions/0012_platform_rpa_contracts.py`.
- Servicio: `backend/app/services/platform_contracts.py`.
- API: `/api/v1/platform-contracts/*`.
- Script: `python scripts\import_arm_first_priority_contracts.py`.
- Demo local importada: 6 manifiestos, 11 cuentas ARM y 306 propuestas de mapeo.
- Todas las cuentas quedan `mode=disabled`, `dry_run=true`, `manual_approval_required=true`, `status=proposal_disabled`.
- Documento: `docs/18_arm_first_priority_contract_development.md`.
- No hay RPA ejecutable ni escrituras externas.

## Panel autorizaciones ARM 2026-05-18

Se implemento un primer panel operativo para visualizar readiness local de ARM:

- API nueva: `GET /api/v1/platform-authorizations/dashboard`.
- Controlador nuevo: `/api/v1/platform-review-schedules/*`.
- Migracion nueva: `backend/alembic/versions/0013_platform_review_schedules.py`.
- Servicio: `backend/app/services/platform_authorizations.py`.
- Servicio: `backend/app/services/platform_review_schedules.py`.
- Frontend historico: `/authorizations` fue retirado el 2026-05-20; sus conceptos pasan a `/platforms`, `/notifications` y `/rpa-gateway`.
- Documento: `docs/19_arm_authorization_dashboard.md`.
- Test nuevo: `test_arm_authorization_dashboard_reports_worker_and_platform_incidents`.
- Test nuevo: `test_platform_review_schedule_controller_configures_intervals`.
- La demo local muestra 6 plataformas prioritarias, 7 trabajadores ARM, 6 schedules de revision y 48 incidencias para actualizar datos en el Hub.
- No lee plataformas externas, no ejecuta RPA y no escribe fuera del Hub.
- Los schedules permiten fijar intervalos por plataforma y calculan `next_run_at`; todos quedan con `dry_run=true` y `manual_approval_required=true`.

## Piloto directo e-coordina 2026-05-18

Se reviso `requisitos/iker_arm_base_legal_operativa_2026-05-18.zip`:

- 20 plataformas ARM.
- 34 cuentas ARM saneadas.
- e-coordina elegida como piloto por tener 6 cuentas ARM, host/URL estable y base operativa completa.
- El paquete no incluye secretos en claro; usa referencias `vault://.../credentials`.

Se ejecuto captura directa de solo lectura sobre ARM/ARITEX:

- Script: `scripts/capture_arm_platform_readonly.py`.
- Fuente: Excel local `USUARIOS Y CONTRASEÑAS PLATAFORMASulo.xlsx`, hoja `ARM`, fila 4.
- Resultado: `login_likely_success`.
- Captcha/MFA: no detectado.
- Contexto: `e-coordina - ARITEX`.
- Artefacto: `artifacts/platform-captures/arm-aritex-20260518-152257/technical_capture.redacted.md`.

Se implemento:

- Migracion nueva: `backend/alembic/versions/0014_platform_review_runs.py`.
- Conector: `backend/app/connectors/rpa/e_coordina/readonly.py`.
- Servicio: `backend/app/services/platform_review_runs.py`.
- Servicio: `backend/app/services/platform_credentials.py`.
- API: `POST /api/v1/platform-review-schedules/{schedule_id}/run-now`.
- API: `GET /api/v1/platform-review-schedules/{schedule_id}/runs`.
- Frontend vigente: los lanzamientos y el historial operativo se consultan desde `/platforms`, `/notifications` y `/rpa-gateway`.
- Runner local: `scripts/run_due_platform_reviews.py`.
- Documento: `docs/20_e_coordina_direct_readonly_pilot.md`.

Resultado del conector directo con credenciales en memoria:

- `status=completed`.
- `result_status=login_likely_success`.
- `captcha_detected=false`.
- `mfa_detected=false`.
- `context_detected=true`.

La ejecucion desde API queda protegida por configuracion: requiere `features.platform_rpa_connectors=true`, `connectors.rpa_enabled=true` y secreto en variables de entorno. No se guardan credenciales, cookies, tokens, HAR, capturas ni cuerpos HTTP.

## Visibilidad estados externos 2026-05-18

Se implemento la primera capa para ver estados documentales externos dentro del Hub:

- API nueva: `GET /api/v1/platform-authorizations/external-statuses`.
- Servicio: `backend/app/services/platform_external_statuses.py`.
- Frontend vigente: los estados e incidencias documentales externas se resumen en `/notifications`.
- El historial de runs muestra resumen tecnico de estados detectados por el conector cuando existen.
- `platform_review_runs.run_schedule_now` queda preparado para persistir observaciones enlazadas a `document_version_id`.
- El conector e-coordina navega en solo lectura a `Documentacion -> Solicitudes de documentacion` y enriquece evidencia con `external_status_summary` desde `documentacion_estado`, sin guardar filas personales, cuerpos HTTP, cookies ni tokens.
- Se reutilizo la tabla existente `external_document_statuses`; no hizo falta migracion.
- Documento: `docs/21_external_status_visibility.md`.
- Documento: `docs/22_e_coordina_status_mapping.md`.
- Lectura live ARITEX confirmada: `Validado=5`, `Caducado=4`, normalizados a `accepted` y `expired_external`.

## Conectores ARM read-only 2026-05-19

Se elevo el resto de plataformas ARM al mismo nivel operativo base que e-coordina, sin activar escritura externa:

- Registro: `backend/app/connectors/rpa/readonly_registry.py`.
- Base comun: `backend/app/connectors/rpa/common_readonly.py`.
- Conectores: `seisconecta`, `ctaima`, `nomio`, `timenet`, `validate`, `vitaly_cae` y `e_coordina`.
- Servicios actualizados: `platform_review_runs`, `platform_review_schedules`, `platform_authorizations` y `rpa_variant_planner` ya consultan el registro en lugar de hardcodear e-coordina.
- Seguridad: un envio maximo de credenciales por ejecucion, `dry_run`, `manual_approval_required`, parada ante captcha/MFA/selector humano, sin proxy/stealth, sin cookies, tokens, HAR, HTML, capturas ni valores de filas.
- Limitacion: solo e-coordina tiene mapeo confirmado de estados agregados (`documentacion_estado`). Las demas plataformas guardan estructura y evidencias redaccionadas hasta aprobar mapeos de columnas y resolucion de entidades.

## Sesion persistente RPA asistida 2026-05-19

Se actualizo `scripts/assisted_platform_browser.py` a `readonly_capture_v8_persistent_session`:

- El backend lanza navegador visible con `launch_persistent_context` y perfil local por cuenta en `storage/rpa-browser-profiles/tenant-{id}/{platform_slug}/{hash}`.
- La siguiente apertura de la misma cuenta reutiliza esa sesion y no reenvia credenciales si la plataforma sigue autenticada.
- Si hay captcha/MFA despues de enviar credenciales, el asistente queda esperando a que el operador lo resuelva y continua la captura cuando desaparece el control.
- El estado de navegador expone solo `session_persistence` redaccionado: perfil reutilizado/no reutilizado y clave hash; no exporta cookies/tokens.
- La pasarela calcula `target_context` por pendiente local o empresa externa y el helper selecciona automaticamente el contexto externo solo cuando hay una coincidencia unica visible, por ejemplo CLIENTE_A en CTAIMA. Si el selector es ambiguo o hay sesion duplicada, el estado queda en `human_context_required`.
- `/api/v1/platform-authorizations/dashboard?priority_group=all` devuelve `account_contexts` y la UI muestra trazas como `CTAIMA / CTAIMA CAE / Empresa Demo Industrial, S.L. en CLIENTE_A,CLIENTE_I,CLIENTE_B,CLIENTE_J,CLIENTE_C` para que todo se revise por plataforma+empresa, no por plataforma agregada.
- Lanzamiento vigente: CTAIMA/CLIENTE_A, run `#9`, perfil `26748c030677bd7a`.

## Mapa de datos plataforma+empresa 2026-05-19

Se implemento `GET /api/v1/platform-maps/data-coverage` y el script
`scripts/build_platform_data_mapping.py` para consolidar el mapa completo de
datos por combinacion plataforma+empresa externa:

- Categorias: empresa, trabajadores, documentos, centros/proyectos,
  maquinaria/vehiculos y acceso/estados.
- Fuentes: manifiestos ARM, propuestas contractuales, mapeos aprobados y
  capturas estructurales redaccionadas.
- No guarda valores de filas externas, cookies, tokens, HTML, HAR ni secretos.
- Artefactos generados: `artifacts/platform-data-mapping/`.
- Resultado local ARM: 7 plataformas, 14 contextos plataforma+empresa, 14
  categorias completas pero pendientes de revision, 69 parciales, 1 sin mapa,
  194 claves obligatorias pendientes y 352 claves pendientes de revision.
- La UI vigente reparte la cobertura por plataforma y empresa entre `/platforms`
  y `/notifications`
  con el siguiente paso por contexto.
- Cada categoria y contexto expone `pending_items` estructurados para GUI con
  severidad, tipo (`missing_required_key`, `pending_mapping_review`,
  `account_not_active`, etc.), clave canonica y accion sugerida. El script
  tambien exporta `platform_data_mapping_pending.redacted.csv`.

## Metodos de edicion por plataforma+empresa 2026-05-19

Se implemento `GET /api/v1/platform-maps/edit-methods` y el script
`scripts/build_platform_field_edit_methods.py` para consolidar, campo a campo,
como debe editar el Hub cada dato en cada contexto plataforma+empresa:

- Fuentes: manifiestos ARM, mapeos revisables y capturas estructurales
  redaccionadas.
- No guarda selectores comerciales inventados; declara estrategia por etiqueta
  observada o nombre estable en ejecucion.
- Estados de campo: `ready_for_preview`, `needs_editable_capture`,
  `needs_mapping_review`, `needs_mapping`, `not_external_edit_target` y
  `credential_secret_only`.
- Operaciones cubiertas: `sync_company_profile`, `upsert_worker`,
  `deactivate_worker`, `upload_worker_document`, `upload_company_document`,
  `upload_machine_vehicle_document` y `sync_assignment`.
- Artefactos generados: `artifacts/platform-edit-methods/`.
- Resultado local ARM: 7 plataformas, 14 contextos plataforma+empresa, 728
  metodos de campo, 30 campos listos para preview, 330 con mapeo a revisar, 242
  sin mapeo y 0 operaciones completas listas para preview.

## Preview de escritura por cuenta 2026-05-20

Se implemento la capa que une mapeo y opcion de escritura externa sin ejecutar
acciones live:

- API nueva: `POST /api/v1/exchange/{account_proposal_id}/preview`.
- Servicio: `backend/app/services/platform_write_previews.py`.
- UI: el mapa de edicion por campo queda como backend/API y se consumira desde
  las acciones de `/platforms` y `/assign-worker`.
- Pasarela: nueva accion segura `capture_write_screen` para mapear pantallas
  editables redaccionadas sin guardar cambios ni subir ficheros.
- Auditoria: cada preview registra `exchange.write_preview` con plataforma,
  entidad, readiness, numero de bloqueos y cambios planificados.

El preview devuelve estado global, contexto plataforma+empresa, entidad local,
campo por campo, valor Hub redaccionado, bloqueos, cambios externos planificados
y siguiente accion. Mantiene `external_write_enabled=false`,
`dry_run_required=true`, `manual_approval_required=true` y auditoria
antes/despues obligatoria hasta que todos los campos de la operacion esten
aprobados y exista una prueba reversible autorizada.

Estado actual tras regenerar matriz:

- 84 operaciones evaluadas.
- 0 operaciones `ready_for_preview`.
- 83 operaciones `needs_mapping_review`.
- 1 operacion `needs_mapping`.
- 30 campos `ready_for_preview`.

Actualizacion 2026-05-20:

- `seisconecta/upsert_worker` tiene perfil especifico por plataforma basado en
  la captura editable real de 6conecta: `worker.identifier_value`,
  `worker.first_name`, `worker.last_name`, `worker.nationality`,
  `worker.contract_type` y `worker.work_position`.
- En el entorno local actual, la cuenta `VELARTIA IGORRE / CONGELADOS DENAVARRA`
  queda `ready_for_preview` para alta de trabajador con esos seis campos; la
  escritura externa live queda habilitada solo para esa cuenta dummy autorizada
  cuando la peticion llega con `dry_run=false`, `manual_approval_required=true`,
  `live_external_write_authorized=true` y `account_proposal_id=8`.
- Prueba live dummy autorizada ejecutada sobre 6conecta:
  - Transfer original: submit ejecutado en navegador visible.
  - Estado vigente tras lectura posterior: `submitted_external_pending_readback`,
    `dry_run=false`, `requires_approval=true`.
  - Trabajador local: `#31 Prueba Live Seisconecta 60535`.
  - Registro local de plataforma: `submitted_pending_readback`, origen
    `connector_rpa_seisconecta_write`.
  - Evidencia de submit:
    `artifacts/external-writes/seisconecta/upsert-worker-31-20260520-063612.status.json`.
  - Evidencia de lectura posterior no confirmada:
    `artifacts/external-writes/seisconecta/readback-worker-31-20260520-v3.status.json`.
  - El helper selecciona empresa autora por scoring de tokens, contrato unico
    disponible por contexto, rellena campos capturados y ejecuta submit en
    navegador visible sin bypass de captcha/MFA.
  - Regla vigente: una escritura externa solo pasa a `confirmed_external` si
    despues del submit hay lectura posterior positiva. En esta prueba el Hub
    informa accion ejecutada, pero no la trata como escritura validada.

La UI ya permite:

- Ver campos listos, pendientes de revision y sin mapa por cada
  plataforma+empresa.
- Ejecutar `Preview empresa` para `sync_company_profile`.
- Lanzar `Capturar editable` para crear una peticion guiada en `/rpa-gateway`
  con `action_key=capture_write_screen`.
- Usar `/assign-worker` para preparar jobs de trabajador/documento en dry-run
  desde el flujo nuevo.

## Conectores RPA de escritura protegida 2026-05-19

Se implemento la primera capa de desarrollo una a una por plataforma:

- Comun: `backend/app/connectors/rpa/common_write.py`.
- Registros: `backend/app/connectors/rpa/write_registry.py`.
- Adaptadores:
  - `e_coordina/write.py`
  - `seisconecta/write.py`
  - `ctaima/write.py`
  - `nomio/write.py`
  - `timenet/write.py`
  - `validate/write.py`
  - `vitaly_cae/write.py`
- Conectores registrados:
  - `connector_rpa_e_coordina_write`
  - `connector_rpa_seisconecta_write`
  - `connector_rpa_ctaima_write`
  - `connector_rpa_nomio_write`
  - `connector_rpa_timenet_write`
  - `connector_rpa_validate_write`
  - `connector_rpa_vitaly_cae_write`
- Cada conector acepta operaciones de trabajador/documento en `dry_run`, genera
  auditoria de preparacion y devuelve `blocked_mapping_review_required` si falta
  mapeo aprobado completo. No ejecuta escritura externa mientras falten esos
  controles.
- La pantalla nueva `/assign-worker` prepara los jobs por trabajador y
  plataforma activa; los conectores reales quedan bloqueados si falta mapeo.

Revision 2026-05-20:

- Documento operativo: `docs/26_worker_platform_write_capability.md`.
- Resultado real: solo `6conecta/upsert_worker` tiene escritura live confirmada
  en cuenta dummy autorizada con lectura posterior positiva. El resto de
  conectores esta registrado pero sigue en preview/dry-run bloqueado por mapeo,
  captura editable pendiente o falta de helper live especifico.
- La alta/edicion local del trabajador se hace desde `/arm`; la publicacion a
  plataformas se prepara desde `/assign-worker`.
- Para cumplir el objetivo de "alta trabajador -> anadir toda su informacion en
  plataformas", falta construir una orquestacion por trabajador que genere
  previews por plataforma+empresa, pida aprobacion y ejecute los jobs live
  disponibles con lectura posterior.

## Superficies de validacion posterior 2026-05-20

Se implemento el mapa de bandejas, notificaciones, pendientes, incidencias y
zonas de lectura posterior por plataforma:

- Servicio: `backend/app/services/platform_validation_surfaces.py`.
- API: `GET /api/v1/platform-maps/validation-surfaces`.
- Script: `scripts/build_platform_validation_surface_map.py`.
- Tests: `backend/tests/test_platform_validation_surfaces.py`.
- Documento: `docs/27_platform_validation_surfaces.md`.
- Artefactos: `artifacts/platform-validation-surfaces/`.

Resultado local ARM:

- 36 capturas vistas, 18 usadas para plataformas ARM actuales.
- 7 plataformas detectadas.
- 129 superficies detectadas.
- 6conecta: trabajador, documentos, homologacion/pendientes, notificaciones y
  accesos.
- e-coordina: trabajador, documento, notificacion, incidentado y acceso.
- Nomio: trabajadores, avisos/notificaciones e incidencias.
- Timenet: trabajadores, gestion de incidencias y estado global.
- Validate y Vitaly CAE: evidencia tecnica minima, falta captura interna
  profunda.
- CTAIMA: capturas persistidas sin bandejas internas; hace falta una captura
  read-only posterior a seleccion de empresa para mapear notificaciones,
  pendientes, validaciones y rechazos.

## Nuevo front operativo 2026-05-20

Se rehizo el flujo principal del frontend desde cero para centrarlo en tres
pantallas:

- `/platforms`: visor de contextos `plataforma + empresa externa + centro`,
  filtros por nombre/plataforma/empresa/centro, activacion/desactivacion de
  revision y formulario de conexion hacia pasarela RPA.
- `/assign-worker`: seleccion o drag/drop de trabajador hacia una o varias
  plataformas activas. Prepara jobs `upsert_worker` y `upload_worker_document`
  para la documentacion actual del trabajador en modo `dry_run` con aprobacion.
- `/notifications`: resumen de avisos solo de plataformas activas, combinando
  pendientes de mapeo/cobertura, incidencias Hub, estado del controlador y
  brechas de lectura posterior.

La navegacion visible queda reducida a `Plataformas`, `Anadir trabajador` y
`Notificaciones`. Las pantallas antiguas siguen existiendo para operativa
profunda, pero no forman parte del flujo principal.

Validado:

```powershell
cd frontend
npm.cmd run typecheck
npm.cmd test
npm.cmd run e2e
```

## Informe datos obtenidos + correspondencias 2026-05-19

Se implemento y ejecuto `scripts/build_platform_obtained_data_mapping_report.py`
para entregar un informe unico con datos obtenidos y correspondencias de campo
por plataforma:

- Artefactos: `artifacts/platform-obtained-mapping/`.
- PDF principal: `platform_obtained_data_mapping_latest.pdf`.
- HTML principal: `platform_obtained_data_mapping_latest.html`.
- JSON estructurado: `platform_obtained_data_mapping_latest.json`.
- CSV de capturas: `platform_obtained_data_index.redacted.csv`.
- CSV de correspondencias: `platform_field_correspondences.redacted.csv`.
- CSV de correspondencias con clave interna: `platform_field_correspondences_mapped.redacted.csv`.
- CSV de estados externos: `platform_external_statuses.redacted.csv`.
- Resultado local ARM: 14 contextos plataforma+empresa, 65 capturas
  redaccionadas, 2001 etiquetas detectadas, 714 correspondencias de mapeo, 3
  observaciones trabajador/plataforma y 0 estados documentales externos
  persistidos en plataformas reales.

Validado:

```powershell
python -m ruff check backend\app backend\tests scripts\import_arm_platform_maps.py scripts\import_arm_first_priority_contracts.py
python -m pytest backend\tests\test_mvp_api.py::test_transfer_demo_and_manual_export_zip -q
python -m pytest backend\tests
$env:PATH = "D:\PLATAFORMAS\.tools\node-v24.15.0-win-x64;$env:PATH"; npm.cmd run typecheck
$env:PATH = "D:\PLATAFORMAS\.tools\node-v24.15.0-win-x64;$env:PATH"; npm.cmd test
```

Limite actual:

- e-coordina ya permite recoger estados reales agregados, pero todavia no persiste estados por documento si no existe un enlace estable y minimizado a una version documental local.

## Estado ARM operativo completo 2026-05-20

Se normalizo la demo local para trabajar solo con ARM y con las plataformas reales del paquete local:

- Script vigente de carga: `python scripts/load_arm_operational_state.py`.
- `scripts/start-product.ps1` ejecuta esa carga antes de levantar frontend/backend.
- Ficha empresa: `Empresa Demo Industrial, S.L.` (`B95868543`), tenant local ARM.
- Trabajadores ARM activos: 7. Se eliminaron trabajadores de prueba generados por validaciones anteriores.
- Propuestas documentales ARM: 39 en `pending_review`, enlazadas a 7 documentos de empresa y 32 documentos de trabajador.
- Documentos internos preparados: 37 ficheros unicos por SHA-256, todos con `status_internal=pending_internal_review`; no se aprueban automaticamente.
- Plataformas ARM configuradas: 20 manifiestos, 34 cuentas/contextos plataforma+empresa, 1020 propuestas de mapeo.
- Schedules activos: 20, todos cada 12 horas, `dry_run=true` y `manual_approval_required=true`.
- Plataformas bloqueadas por host pendiente: Quironprevencion y Sarenet; quedan visibles y no deben ejecutarse hasta resolver URL/host.

## Front ARM/Operativa 2026-05-20

Se rehizo la entrada principal del frontend para separar datos propios ARM de operativa de plataformas:

- `/` redirige a `/arm`.
- `/arm` muestra ficha empresa ARM, listado de trabajadores y resumen de documentos internos.
- La navegacion lateral tiene seccion `ARM` para datos propios y seccion `Operativa` para plataformas, alta de trabajador en plataformas y notificaciones.
- Login y selector de empresa conservan el `next`, pero por defecto entran en `/arm`.
- Si una API devuelve `401`, el frontend limpia token/empresa local y redirige a `/login?next=...`, evitando pantallas vacias con `Invalid access token`.
- Ajuste posterior: las evidencias pendientes de validacion ya no aparecen en `/arm`; se muestran en `/notifications` como avisos operativos.
- `/arm` permite editar la empresa ARM, abrir cada trabajador, editar sus datos operativos/RGPD minimizados y subir nuevas versiones documentales normalizadas para empresa o trabajador. La subida usa `DocumentType` existente; no se crean tipos libres desde la UI.
- Tipos normalizados de trabajador conocidos en la demo ARM: `ARM.WORKER.TRAINING_EVIDENCE`, `CAE.WORKER.BASIC_PRL_COURSE`, `CAE.WORKER.ID_DOCUMENT`, `CAE.WORKER.MEDICAL_FITNESS`, `CAE.WORKER.PPE_DELIVERY` y `CAE.WORKER.RISK_INFORMATION`.

Actualizacion UX/documental:

- `/arm` ya no muestra empresa y trabajador a la vez. La vista principal separa
  `Empresa ARM` y `Trabajadores`.
- Al abrir `Empresa ARM` se ve la ficha de empresa, subida de documento de
  empresa y tabla de documentos de empresa con ultima subida, version, origen,
  caducidad empresa/plataforma, SHA parcial, tamano y descarga de la ultima
  version.
- En `Trabajadores` primero se muestra el listado; cada trabajador se abre en
  una ficha propia con boton `Volver al listado`, datos editables, subida de
  documento de trabajador y tabla documental del trabajador.
- Se corrigio la normalizacion ARM para no agrupar evidencias distintas bajo
  `Curso basico PRL`. Los tipos de formacion adicionales son:
  `CAE.WORKER.PRL_50H_COURSE`, `CAE.WORKER.PRL_ART19`,
  `CAE.WORKER.METAL_TRAINING`, `CAE.WORKER.METAL_RECYCLING`,
  `CAE.WORKER.FORKLIFT_TRAINING`, `CAE.WORKER.MEWP_TRAINING`,
  `CAE.WORKER.OVERHEAD_CRANE_TRAINING` y
  `CAE.WORKER.HEIGHT_WORKS_TRAINING`.
- Estado local tras recargar ARM: 1 documento sigue como `Curso basico PRL`, 2
  como `Curso PRL 50 horas`, 5 como `Formacion PRL Art. 19`, 5 como
  `Formacion carretilla elevadora`, 5 como `Formacion metal`, 3 como
  `Formacion plataforma elevadora`, 2 como `Formacion puente grua`, 2 como
  `Formacion trabajos en altura` y 3 como `Reciclaje metal`.

Validado:

```powershell
cd frontend; npm.cmd run typecheck
cd frontend; npm.cmd test
cd frontend; npm.cmd run e2e
cd backend; python -m pytest tests -q
cd backend; python -m ruff check app tests
cd backend; python -m mypy app
```

Comprobacion API local:

- Empresas: 1.
- Trabajadores: 7.
- Documentos: 37.
- Propuestas documentales: 39.
- Plataformas/manifiestos: 20.
- Cuentas/contextos plataforma+empresa+centro: 34.

## Pruebas de escritura segura ARM 2026-05-20

Se anadio cobertura funcional para validar las plataformas ARM con conector de
escritura registrado sin ejecutar escrituras externas comerciales directas:

- Test funcional: `test_arm_available_write_platforms_preview_only_and_human_assisted`.
- Cubre cuentas ARM de `ctaima`, `e_coordina`, `nomio`, `seisconecta`,
  `timenet`, `validate` y `vitaly_cae`.
- Para cada cuenta disponible se ejecuta `POST /api/v1/exchange/{account}/preview`
  sobre `upsert_worker`, comprobando que la salida mantiene
  `external_write_enabled=false`, `dry_run_required=true`,
  `manual_approval_required=true`, auditoria antes/despues obligatoria,
  sin bypass de captcha/MFA y sin almacenar selectores o credenciales.
- Para cada conector registrado se prueba `POST /api/v1/transfers` en
  `dry_run=true` y aprobacion humana, verificando que no se marque como
  escritura externa valida mientras no exista lectura posterior confirmada.
- La pasarela humana queda validada con `capture_write_screen`: crea flujo
  `human_action_required`, no escribe en el sistema externo y conserva controles
  seguros para que el operador resuelva captcha, MFA o avisos legales en
  navegador visible.

Validado:

```powershell
cd backend; python -m pytest tests\test_mvp_api.py::test_arm_available_write_platforms_preview_only_and_human_assisted -q
cd backend; python -m pytest tests -q
cd backend; python -m ruff check app tests
cd backend; python -m mypy app
cd frontend; npm.cmd run typecheck
cd frontend; npm.cmd test
cd frontend; npm.cmd run e2e
```

Actualizacion alta trabajador CTAIMA 2026-05-20:

- Se anadio prechequeo de duplicado en `POST /api/v1/transfers` para
  `upsert_worker`: si el trabajador ya tiene `WorkerPlatformRegistration` en la
  misma plataforma/cuenta con estado externo vigente, el Hub devuelve `409` y no
  crea un job de alta.
- El bloqueo no aplica a `connector_manual_export`, porque generar un paquete
  manual no es ejecutar un alta externa.
- Prueba local: Alicia Gomez en CTAIMA/CLIENTE_A devuelve
  `No se puede dar de alta el trabajador porque ya existe en esta plataforma/cuenta.
  Estado actual: missing_required_document.`
- Peticion relanzada para CTAIMA/GRUPO: job `#22`, estado
  `blocked_mapping_review_required`, `dry_run=true`, sin escritura externa.
- Pasarela creada para mapear pantalla editable CTAIMA/GRUPO: run `#11`,
  operacion `capture_write_screen`, navegador visible lanzado, perfil persistente
  `762e876fc1c593e7`, estado `waiting_for_login_form`. No se ha guardado ni
  enviado ningun formulario externo.

Actualizacion revision global plataformas 2026-05-20:

- Se regeneraron los mapas actuales:
  - `scripts/build_platform_data_mapping.py --priority-group all`: 20
    plataformas, 34 contextos, 1.360 pendientes de datos/mapeo.
  - `scripts/build_platform_field_edit_methods.py --priority-group all`: 1.768
    metodos de campo, 40 campos listos para preview y 1 operacion completa
    lista a nivel de mapeo.
  - `scripts/build_platform_validation_surface_map.py --include-all`: 8
    plataformas con capturas, 36 capturas usadas y 147 superficies de
    validacion/readback.
  - `scripts/build_platform_operation_catalog.py`: 53 plataformas detectadas en
    catalogos/capturas/contratos, 423 entradas operativas y 0 escrituras
    externas verificadas.
- Nuevo script seguro:
  `scripts/probe_platform_write_previews.py --connector-dry-run`. Genera
  `artifacts/platform-write-probes/platform_write_probe_latest.{json,csv,md}`.
  En la ejecucion actual probo 238 combinaciones contexto/operacion sobre 34
  contextos y 20 plataformas. Resultado: 0 filas `preview_ready`, 203 bloqueos
  por mapeo, 1 bloqueo por dato local, 34 saltadas por falta de version
  documental compatible, 14 dry-runs de conector bloqueados correctamente y 0
  escrituras externas ejecutadas.
- Causa principal del bloqueo actual: los trabajadores ARM locales no tienen
  todavia identificador, nacionalidad, contrato o puesto operativo suficientes
  para preparar altas reales; ademas la mayoria de plataformas tienen campos de
  escritura pendientes de revisar/capturar.
- `/platforms` muestra ahora tambien estado de escritura por contexto: numero de
  contextos con preview disponible, estado de `upsert_worker` (`preview listo`,
  `falta captura`, `revisar mapeo`, `sin mapeo`) y siguiente accion.

Actualizacion escritura live 6conecta 2026-05-20:

- Trabajador de prueba creado en Hub: `#23 Prueba Hub Autorizada No Usar`
  (`99999999R`, ultimo bloque `999R`).
- Cuenta usada: 6conecta propuesta `#8`, plataforma/cuenta `#8`,
  `VELARTIA IGORRE / CONGELADOS DENAVARRA`.
- Preview previo: `preview_ready` para `upsert_worker`.
- Escrituras live ejecutadas: transfers `#25` y `#26`, ambos con
  `dry_run=false`, `manual_approval_required=true`,
  `live_external_write_authorized=true` y estado
  `submitted_external_pending_readback`.
- Lectura posterior: no confirmada; el Hub no considera estas acciones como
  `valid_external_write`.
- Evidencias:
  `artifacts/external-writes/seisconecta/upsert-worker-23-20260520-201848.status.json`,
  `artifacts/external-writes/seisconecta/readback-worker-23-20260520-202345.status.json`
  y `artifacts/external-writes/seisconecta/upsert-worker-23-20260520-202654.status.json`.
- Correccion aplicada: `POST /api/v1/transfers` devuelve ahora `TransferRead`
  con `last_attempt_status`, `post_write_read_confirmed`,
  `valid_external_write` y `status_artifact` inmediatamente despues de crear el
  job. Tambien persiste `platform_account_id` en jobs de trabajador y el bloqueo
  de duplicados cubre registros antiguos con `platform_account_id` nulo.
- Estado operativo: no lanzar otra alta live de ese trabajador/cuenta hasta
  mejorar la lectura posterior o cerrar manualmente la validacion externa.

Actualizacion global escritura RPA 2026-05-21:

- Se aplico el mismo contrato de escritura protegida a todos los conectores RPA
  registrados. Si una plataforma no tiene helper live especifico y se intenta
  `dry_run=false`, devuelve `blocked_live_adapter_missing` con
  `external_write_executed=false`, `post_write_read_confirmed=false` y
  `valid_external_write=false`.
- Se regenero `scripts/probe_platform_write_previews.py --connector-dry-run`:
  20 plataformas, 34 contextos, 238 operaciones, 1 `preview_ready`, 169
  `blocked_mapping_review_required`, 68 `skipped_no_document_version` y 0
  escrituras externas ejecutadas.
- Artefactos:
  `artifacts/platform-write-probes/platform_write_probe_20260521-063747.json`,
  `.csv`, `.md` y alias `platform_write_probe_latest.*`.
- Estado de helper live: 7 filas con helper especifico disponible, 91 con
  `blocked_live_adapter_missing` y 140 sin conector de escritura registrado.
- Unica operacion lista: `6conecta / VELARTIA IGORRE / CONGELADOS DENAVARRA /
  upsert_worker`.
- Para CTAIMA, e-coordina, Nomio, Timenet, Validate, Vitaly CAE y el resto de
  plataformas, el siguiente paso obligatorio es capturar pantalla editable,
  aprobar mapeo de campos y definir lectura posterior. No se ha escrito en esas
  plataformas porque no hay evidencia suficiente para hacerlo sin inventar.

Actualizacion rutas Exchange 2026-05-21:

- Se extrajo la matriz de escritura a
  `backend/app/services/platform_write_probe_matrix.py`; el script
  `scripts/probe_platform_write_previews.py` ahora usa ese servicio.
- Nuevas rutas:
  - `GET /api/v1/exchange/write-matrix` para readiness por
    cuenta+operacion, estado de helper live y dry-run de conector sin escritura
    externa.
  - `GET /api/v1/exchange/live-adapters` para listar conectores registrados,
    operaciones soportadas y requisito pendiente antes de live.
  - `POST /api/v1/exchange/capture-write-screens/bulk` para crear pasarelas de
    captura editable en todas las cuentas/plataformas filtradas, evitando
    duplicados activos.
  - `POST /api/v1/exchange/workers/bulk-submit` para preparar alta de un
    trabajador en todas las cuentas con conector, creando jobs dry-run y, si se
    pide, peticiones `capture_write_screen` para mapear pantallas pendientes.
  - `POST /api/v1/exchange/{account_proposal_id}/submit` para enviar una
    operacion desde cuenta externa sin que el front tenga que conocer
    `platform_key` ni `connector_key`; la ruta exige preview y delega en
    transferencias auditadas.
  - `POST /api/v1/exchange/{account_proposal_id}/capture-write-screen` para
    crear directamente una pasarela `capture_write_screen` desde la cuenta.
- Test ampliado:
  `test_arm_available_write_platforms_preview_only_and_human_assisted` valida
  las rutas Exchange nuevas, confirma 20 plataformas, 7 conectores registrados,
  1 helper live especifico, bloqueo `blocked_live_adapter_missing` en el resto
  alta masiva dry-run con peticiones de captura por cuenta y submit dry-run por
  cuenta CTAIMA resuelto automaticamente a `connector_rpa_ctaima_write`.
- Skill local creado para continuidad:
  `C:/Users/ikerh/.codex/skills/iprl-cae-platform-write-method` y validado con
  `quick_validate.py`.

Actualizacion alta masiva 2026-05-21:

- Se implemento `POST /api/v1/exchange/workers/bulk-submit`.
- Prueba local live autorizada contra trabajador `#19 Prueba Hub Escritura
  Final`:
  - 14 cuentas con conector evaluadas.
  - Transfer live creado: `#34` contra 6conecta/cuenta `#8`.
  - Resultado 6conecta: `already_exists_external`; la lectura previa/posterior
    encontro el trabajador ya existente y el Hub bloqueo alta duplicada.
  - Registro local resultante: `WorkerPlatformRegistration #5`, 6conecta,
    estado `confirmed`, `platform_account_id=8`.
  - Para el resto se crearon 13 peticiones de pasarela
    `capture_write_screen`, runs `#12` a `#24`, todas
    `human_action_required`, para mapear pantalla editable antes de cualquier
    escritura real.

Actualizacion prueba Alicia 2026-05-21:

- Trabajador probado: `#11 Alicia Gomez`.
- Matriz previa: 0 cuentas `preview_ready`; Alicia no tiene en ARM datos
  obligatorios para alta (`identifier_value`, nacionalidad, contrato, puesto y
  otros campos segun plataforma).
- Prueba live autorizada con `POST /api/v1/exchange/workers/bulk-submit`:
  - 14 cuentas con conector evaluadas.
  - 0 escrituras externas ejecutadas.
  - CTAIMA/CLIENTE_A (`account_proposal_id=14`) devolvio
    `already_exists_external`: "No se puede dar de alta el trabajador porque ya
    existe en esta plataforma/cuenta. Estado actual: missing_required_document."
  - 6conecta quedo `blocked_submit` por `blocked_local_data_required`.
  - Resto de cuentas quedo `blocked_submit` por `blocked_mapping_review_required`
    y/o falta de helper live especifico.
  - Se crearon 13 nuevas peticiones `capture_write_screen`, runs `#25` a `#37`,
    para mapear pantallas editables donde no hay contrato live suficiente.

Actualizacion pasarelas globales 2026-05-21:

- Se ejecuto `POST /api/v1/exchange/capture-write-screens/bulk` contra todas
  las cuentas ARM.
- Resultado: 34 cuentas evaluadas, 20 pasarelas nuevas creadas, 14 omitidas por
  tener ya una pasarela activa, 0 fallos.
- Nuevas runs: `#38` a `#57`.
- No se lanzo navegador ni se ejecuto escritura externa. Las runs quedan en
  `human_action_required` para que el operador abra cada plataforma, resuelva
  captcha/MFA si aparece y permita capturar la pantalla editable real.

Actualizacion pruebas live y captura masiva 2026-05-21:

- Escritura real validada en `6conecta`:
  - Trabajador local `#26 Prueba Hub Lote Escritura 20260521`.
  - Transfer `#35`, `dry_run=false`, `manual_approval_required=true`.
  - Estado `confirmed_external`, `post_write_read_confirmed=true`,
    `valid_external_write=true`.
  - Registro local `WorkerPlatformRegistration #6`, `platform_account_id=8`,
    `external_worker_id=5710689`.
  - Evidencia redaccionada:
    `artifacts/external-writes/seisconecta/upsert-worker-26-20260521-082557.status.json`.
- Se lanzaron pasarelas visibles `capture_write_screen` para la ultima cuenta
  disponible por plataforma+empresa/centro con URL valida. Capturas
  sincronizadas: `#14`, `#25`, `#26`, `#28`, `#29`, `#30`, `#32`, `#33`,
  `#34`, `#37`, `#38`, `#39`, `#40`, `#45`, `#46`, `#47`, `#48`, `#49`,
  `#51`, `#53`, `#54`, `#55`, `#56`, `#57`.
- Quedan con intervencion humana o login/contexto pendiente: `#27` CTAIMA/Cliente D,
  `#31` Vitaly CAE/SEDA, `#35` y `#36` e-coordina, `#41` y `#42` IEDOCE,
  `#43` y `#44` Integra ASEM.
- `#50` Quironprevencion y `#52` Sarenet quedan bloqueadas por configuracion:
  las cuentas tienen `PENDIENTE_URL/PENDIENTE_HOST`; no se puede probar sin URL
  autorizada real y no se deben inventar rutas.
- Se corrigio el helper de navegador para:
  - Bloquear `entry_url` no HTTP/HTTPS antes de lanzar navegador.
  - Sustituir el estado anterior cuando una pasarela no se lanza.
  - Registrar errores de navegacion inicial como estado operable en vez de dejar
    el flujo congelado en `browser_launched`.
  - Usar un mensaje generico de mapeo pendiente, no especifico de CTAIMA, en
    plataformas distintas.

Actualizacion importacion PRL ARM 2026-05-21:

- Se creo el flujo local de importacion de paquetes PRL/CAE de empresa:
  `scripts/import_company_prl_archive.py`.
- La logica reutilizable vive en
  `backend/app/services/company_prl_archive_import.py`.
- El ZIP objetivo actual es
  `requisitos/wetransfer_arm_2026-05-21_0759.zip`.
- El importador:
  - inventaria ZIPs y ZIPs anidados;
  - omite formatos no soportados como `.rar` y `.db` con motivo en reporte;
  - crea/actualiza ARM y trabajadores detectados por carpeta;
  - clasifica documentos de empresa y trabajador por ruta, nombre y texto
    seguro cuando existe;
  - guarda ficheros por almacenamiento documental con SHA-256;
  - crea `DocumentIntake` en `pending_review`;
  - crea `Document`/`DocumentVersion` en `pending_internal_review`.
- Se amplio OCR/intake para DOCX basico por XML interno.
- Se creo documentacion en `docs/14_company_prl_archive_import.md`.
- Se creo el skill local
  `iprl-cae-company-prl-onboarding` para repetir este proceso.
- La pantalla `/arm` se refuerzo para ver empresa y trabajadores por separado,
  filtrar documentos, ver ultima version, fecha de subida, caducidad, tamano,
  hash y descargar el ultimo fichero.
- Revision posterior de migracion: los tres `.rar` del ZIP ARM contienen
  documentos mensuales de empresa (RLC/TC1, RNT/TC2, ITA, justificantes y
  certificados de Seguridad Social/Hacienda). Se extrajeron a
  `artifacts/arm-prl-import/rar-db-analysis/extracted/` y se importaron mediante
  `arm_prl_rar_extracted_docs.zip`. Los dos `.db` son `Thumbs.db`, cache de
  miniaturas de Windows, y no se importan como evidencia.
- Por instruccion explicita del usuario, se anadio
  `scripts/approve_arm_imported_documents.py` y se aceptaron las propuestas
  documentales ARM con auditoria. Estado local final: 10 trabajadores reales
  ARM, 117 documentos en `valid_internal` y 173 intakes en `accepted`.
- Se corrigio el importador para que un paquete solo de documentos de empresa
  no pueda limpiar trabajadores existentes. Tambien se cambio el seed local para
  no reinsertar trabajadores placeholder cuando ARM ya tiene trabajadores
  migrados.

Actualizacion plataformas vigentes ARM 2026-05-21:

- Se sincronizo `requisitos/usuarios y contraseñas PLATAFORMAS.xlsx` como
  fuente vigente de cuentas operativas.
- Resultado local: 30 cuentas activas, 4 cuentas marcadas `baja`.
- Cuentas `baja`: Nomio/NOMIO, Timenet/TIMENET, Quironprevencion/QUIRON y
  Sarenet/SARENET.
- Las cuentas `baja` quedan con `mode=disabled`, schedule deshabilitado y no
  generan incidencias/avisos operativos.
- Las cuentas activas quedan con revision segura cada 12h, `dry_run=True` y
  `manual_approval_required=True`.
- A peticion posterior del usuario, las credenciales del Excel vigente se
  conservan en DB cifradas con referencia `enc:v1` en
  `PlatformRpaAccountProposal.credential_secret_ref`; `PlatformAccount` guarda
  una referencia interna `db://...` y los logs/auditoria siguen redactando
  secretos. Resultado local final: 30 cuentas activas con credencial cifrada,
  4 cuentas `baja`, 16 schedules habilitados y 4 deshabilitados.
- Se anadio `scripts/sync_current_platform_accounts.py` para repetir la
  sincronizacion.
- Se anadio `scripts/report_platform_write_readiness.py` para generar la matriz
  de capacidad de alta de trabajador sobre cuentas activas.
- Ultimo reporte generado:
  `artifacts/platform-write-readiness/current_platform_write_readiness_20260521_094459.md`.
- Matriz actual: 30 contextos activos revisados; 0 permiten alta real inmediata
  con los datos ARM actuales; 1 tiene helper live especifico (`6conecta`) pero
  queda bloqueado por datos ARM obligatorios incompletos; 11 tienen conector de
  escritura generico pero falta helper live/mapeo; 18 no tienen conector de
  escritura registrado.

Actualizacion accesos/mapeo 2026-05-21 10:09:

- Se anadio `scripts/launch_platform_capture_flows.py` para repetir el proceso
  completo de captura editable: crea pasarela si falta, registra autorizacion
  humana, lanza navegador visible con credenciales configuradas y sincroniza la
  captura disponible. No ejecuta escrituras externas.
- Los scripts `probe_platform_write_previews.py` y
  `build_platform_field_edit_methods.py` ya no ejecutan el seed por defecto;
  usar `--seed` solo cuando se quiera regenerar datos demo conscientemente.
- `proposal_disabled` se trata como estado inactivo en matrices operativas.
- Se resincronizo `usuarios y contraseñas PLATAFORMAS.xlsx`: 30 cuentas activas
  con credencial cifrada y 4 cuentas `baja`.
- Ultimo lanzamiento/sincronizacion:
  `artifacts/platform-access-launches/platform_access_launch_20260521_100900.md`.
  Resultado: 30 cuentas objetivo, 30 navegadores ya lanzados, 22 capturas
  sincronizadas, 8 sin captura disponible todavia, 0 escrituras externas.
- Las capturas sincronizadas generan propuestas de mapeo `field` en
  `pending_review` cuando hay etiqueta reconocible; no se aprueban
  automaticamente.
- Ultima matriz de alta:
  `artifacts/platform-write-readiness/current_platform_write_readiness_20260521_100909.md`.
  Resultado: 0 altas reales inmediatas; `6conecta` sigue bloqueada por datos
  locales ARM obligatorios incompletos (nacionalidad, contrato y puesto del
  trabajador candidato), el resto por mapeo/helper o ausencia de conector.

## Pendientes recomendados

Prioridad alta:

1. Definir enlace seguro entre fila documental e-coordina y `document_version_id` para persistir estados automaticamente.
2. Conectar `platform_review_schedules` a jobs persistentes Redis/RQ o Celery; ya existe runner local transitorio.
3. Convertir incidencias de `/notifications` en acciones preparables con preview por plataforma.
4. Convertir importaciones ERP en jobs persistentes con Redis/RQ o Celery.
5. Crear historial de importaciones ERP con preview, aprobacion, errores por fila y auditoria de lote.
6. Mejorar UI de edicion inline de cursos, obras y plataformas; ahora se puede crear/borrar y el backend soporta `PUT`.
7. Completar CRUD de maquinaria, vehiculos y equipos.
8. Completar permisos por proyecto/centro, no solo por empresa.
9. Llevar Playwright a mas flujos: signup, onboarding empresa, OCR approve, configuracion empresa, cambio multiempresa.

Prioridad media:

1. Cola de OCR asincrona con Redis.
2. Vista de historial/auditoria mas filtrable.
3. Configuracion tenant de conectores ERP desde backend/configuracion segura; no hay pantalla `/admin` vigente.
4. Tests de arranque server con config real simulada.
5. Preparar instalacion systemd con comprobaciones de PostgreSQL/Redis.

No hacer todavia:

- Conectores comerciales reales.
- RPA contra terceros.
- Guardar secretos en `config/`, `README`, tests o logs.
- Cambiar a Docker.

## Nota final para la siguiente sesion

Si la proxima tarea es continuar desarrollo, empezar por:

```powershell
cd D:\PLATAFORMAS
Get-Content AGENTS.md
Get-ChildItem docs -File | Sort-Object Name | ForEach-Object { Get-Content $_.FullName }
python -m pytest backend\tests
```

Despues arrancar el producto local si se necesita UI:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-product.ps1
```
