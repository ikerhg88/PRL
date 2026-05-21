# 19 - Panel de autorizaciones ARM

Fecha: 2026-05-18.

## Objetivo

Dar una vision operativa de ARM frente a las plataformas prioritarias sin acceder todavia a sistemas externos:

- Estado global verde/naranja/rojo.
- Estado por plataforma prioritaria.
- Capacidad por plataforma: si se puede leer, si se puede escribir y que autorizacion/configuracion falta.
- Estado por trabajador.
- Incidencias accionables para corregir datos en el Hub.
- Enlaces locales para actualizar trabajador, documentos o mapeos antes de preparar futuras subidas.

## Alcance implementado

Backend:

- Servicio: `backend/app/services/platform_authorizations.py`.
- API: `GET /api/v1/platform-authorizations/dashboard`.
- Router: `backend/app/api/platform_authorizations.py`.
- Esquemas: `PlatformAuthorizationDashboardRead` y modelos relacionados en `backend/app/schemas.py`.
- Test: `test_arm_authorization_dashboard_reports_worker_and_platform_incidents`.

Frontend:

- Vista: `/authorizations`.
- Vista: `/` reutiliza los mismos datos para mostrar el estado por plataforma de empresa/trabajadores y los filtros operativos.
- Navegacion: grupo `Plataformas` -> `Autorizaciones`.
- Tablas:
  - lectura/escritura/autorizacion por plataforma;
  - frecuencia de revision por plataforma;
  - plataformas prioritarias ARM;
  - trabajadores ARM;
  - incidencias con accion local.

## Semaforo

`green`:

- La entidad local no tiene incidencias detectadas.
- Los documentos vigentes tienen version inmutable.
- La aptitud laboral minimizada esta presente y vigente.

`orange`:

- Falta dato no bloqueante.
- Hay documentos pendientes de revision.
- Hay mapeos de plataforma pendientes de aprobacion.
- La plataforma esta en propuesta deshabilitada, como corresponde en esta fase.

`red`:

- Falta identificador esencial.
- Falta aptitud laboral.
- Documento caducado/rechazado.
- Host/URL de plataforma pendiente o cuenta bloqueada por informacion tecnica incompleta.

## Fuente de datos

La API consolida principalmente datos locales:

- `companies`.
- `workers`.
- `documents` y `document_versions`.
- `worker_platform_registrations`.
- `external_document_statuses`, si existen.
- `platform_rpa_manifests`.
- `platform_rpa_account_proposals`.
- `platform_rpa_mapping_proposals`.
- `platform_review_schedules`.
- `platform_review_runs`.

Por defecto no se leen credenciales, no se abren navegadores externos, no se guardan cookies y no se ejecutan escrituras fuera del Hub. El piloto e-coordina puede lanzar una lectura real solo si el servidor activa expresamente conectores RPA y resuelve credenciales desde entorno seguro; aun asi no guarda cookies, tokens, HAR, capturas ni cuerpos HTTP.

## Plataformas incluidas

El endpoint usa por defecto `priority_group=arm_first_priority`, importado desde contratos revisables:

- e-coordina.
- 6conecta.
- Validate.
- Timenet.
- Nomio.
- Vitaly CAE.

## Incidencias y actualizacion local

Cada incidencia devuelve:

- `severity`.
- `platform_name`, si aplica.
- `entity_type` y `entity_id`.
- `title` y `detail`.
- `suggested_action`.
- `local_update_path`.
- `source=hub_local_readiness`.

Los enlaces actuales apuntan a vistas internas:

- `/workers?worker_id={id}` para fichas de trabajador.
- `/documents` para documentos de empresa/trabajador.
- `/authorizations` para readiness y runs; `/admin` para cuentas y permisos de plataforma.

## Matriz de capacidad por plataforma

La primera tabla operativa de `/authorizations` responde directamente:

- `Leer datos`: verde si hay lectura verificada, naranja si falta activar/probar y rojo si no hay conector, cuenta, host o configuracion suficiente.
- `Escribir datos`: rojo mientras la plataforma este en propuesta, `dry_run` o aprobacion manual. En esta fase no hay escritura externa activa.
- `Autorizacion`: naranja cuando falta autorizacion firmada o activacion de contrato/cuenta; rojo si falta un dato bloqueante como host/URL.
- `Siguiente paso`: accion concreta para pasar al siguiente estado sin saltarse controles.

La matriz se calcula desde manifiestos ARM, cuentas propuestas, mapeos, schedules y ultimo resultado de lectura. No inventa endpoints ni declara escritura disponible si solo existe plan/dry-run.

El visor `Pendiente por plataforma y empresa` incluye `Recargar datos` por fila. La accion crea una peticion en `/rpa-gateway?request={id}` con `manual_approval_required=true`, selecciona la cuenta ARM disponible para esa combinacion plataforma+empresa externa (CTAIMA prioriza CLIENTE_A cuando existe esa observacion), y enfoca directamente un flujo guiado. La pasarela muestra objetivo, cuenta, host autorizado, credenciales configuradas en servidor y estado del navegador visible. Al autorizar, el backend lanza un navegador guiado con credenciales resueltas en memoria; si aparece selector de empresa/cuenta, el helper selecciona automaticamente solo cuando el contexto objetivo aprobado produce una coincidencia unica visible. Si aparece captcha, MFA, sesion duplicada, selector ambiguo o aviso legal, la resolucion corresponde al operador delante de pantalla y el asistente espera para continuar. Si la plataforma permite entrar, el helper recoge estructura redaccionada de solo lectura y habilita `Sincronizar lectura con Hub`, que guarda evidencia `gateway.readonly_capture` sin escrituras externas. El Hub solo registra la decision y mantiene `changes_applied=[]`; la escritura o persistencia fila a fila queda bloqueada hasta tener mapeo aprobado.

## Mapa de datos por plataforma y empresa

La seccion `Cobertura por plataforma y empresa` usa
`GET /api/v1/platform-maps/data-coverage` para mostrar, por cada contexto
externo, si estan cubiertas las categorias de empresa, trabajadores,
documentos, centros/proyectos, maquinaria/vehiculos y acceso/estados.

El mapa combina:

- Etiquetas observadas en capturas redaccionadas.
- Propuestas de contrato RPA.
- Mapeos aprobados manualmente.

No extrae ni muestra valores de filas externas. Si una categoria esta parcial o
sin mapa, la accion correcta es lanzar captura guiada de solo lectura o aprobar
las equivalencias pendientes antes de permitir persistencia fila a fila.

## Estrategia RPA por plataforma

La vista tambien lee `GET /api/v1/platform-review-schedules/rpa-variant-plan`
para mostrar todas las plataformas ARM actuales, incluidas las que no estan en
primera prioridad. Este plan no accede a terceros: consolida cuentas, hosts,
credenciales disponibles como booleano, schedules, ultimo resultado, mapeos y
snapshot local ARM.

Por cada plataforma se muestran multiples variantes seguras:

- Login en una pantalla.
- Login en dos pasos.
- Sesion ya abierta o reanudada.
- Handoff humano para captcha/MFA/aviso/sesion duplicada.
- Confirmacion de empresa/cuenta autorizada.
- Confirmacion de cliente/proyecto cuando aplique.
- Captura read-only redaccionada.
- Mapeo fila a fila bloqueado hasta aprobacion.
- Fallback de exportacion/manual follow-up.

La politica es deliberadamente conservadora: no hay intentos paralelos, no hay
selector guessing, se limita a un envio de credenciales por cuenta y ejecucion,
y se detiene ante captcha, MFA, aviso legal, sesion duplicada, rate limit,
empresa inesperada o pantalla no reconocida. El objetivo es ofrecer una accion
sencilla al usuario sin convertir la robustez en bypass ni riesgo de bloqueo de
cuenta.

## Controlador de revision

El panel incluye un controlador por plataforma para definir cada cuanto debe revisarse una fuente externa cuando la fase de lectura autorizada este activa.

Backend:

- Tabla: `platform_review_schedules`.
- Migracion: `0013_platform_review_schedules`.
- API:
  - `GET /api/v1/platform-review-schedules`.
  - `POST /api/v1/platform-review-schedules/ensure`.
  - `POST /api/v1/platform-review-schedules/activate-12h`.
  - `GET /api/v1/platform-review-schedules/health`.
  - `PATCH /api/v1/platform-review-schedules/{schedule_id}`.
  - `POST /api/v1/platform-review-schedules/{schedule_id}/run-now`.
  - `GET /api/v1/platform-review-schedules/{schedule_id}/runs`.

Campos principales:

- `enabled`: activa o pausa la planificacion.
- `interval_minutes`: frecuencia de revision, con minimo tecnico de 15 minutos.
- `review_scope`: bloques a revisar (`company`, `workers`, `documents`, `incidents`, `mappings`).
- `next_run_at`: proxima revision calculada al activar o cambiar intervalo.
- `dry_run=true` y `manual_approval_required=true`: se mantienen forzados en esta fase.

La pantalla permite intervalos de 1h, 4h, 12h, 24h y 7 dias. Tambien incluye `Activar 12 h`, que deja todas las plataformas ARM prioritarias programadas cada 720 minutos con `dry_run=true` y `manual_approval_required=true`. El estado de salud del modulo muestra por plataforma si esta `working`, `not_working`, `not_checked` o `not_configured`, con el motivo concreto.

Tambien expone `Probar lectura`: solo ejecuta RPA real si la configuracion del servidor activa conectores RPA y existe una referencia de secreto resoluble; en caso contrario registra un run bloqueado sin acceder a terceros.

La misma vista muestra el historial de las ultimas ejecuciones:

- `status`: estado tecnico del run.
- `result_status`: resultado normalizado (`rpa_disabled`, `login_likely_success`, `human_action_required`, etc.).
- `result_summary`: resumen operativo sin secretos.
- `trigger_source`: origen manual o runner programado.

## Observaciones humanas de plataforma

Cuando una plataforma no se puede leer de forma automatica por captcha/MFA/control, el Hub puede mostrar una observacion humana estructurada en `worker_platform_registrations` sin marcarla como lectura externa verificada.

Caso vigente ARM:

- Plataforma: CTAIMA / CTAIMA CAE.
- Cuenta: CLIENTE_A, fila ARM 29.
- Trabajador: Alicia Gomez.
- Pendiente: falta `Entrega de EPIs`.
- Estado local: `missing_required_document`, rojo.
- Fuente: observacion manual ARM y flujo asistido CTAIMA. La prueba tecnica inicial del 2026-05-19 quedo en `stopped_control_detected_before_login`; en la repeticion guiada el operador logro entrar, pero los relanzamientos posteriores quedaron bloqueados por control de sesion duplicada de CTAIMA (`Ya existe una sesion activa`). El Hub puede sincronizar esa lectura como evidencia redaccionada, sin secretos, cookies, tokens, HAR, cuerpos HTTP ni capturas, pero no persiste filas de trabajador/documento hasta aprobar el mapeo CTAIMA -> Hub.

Runner local para schedules vencidos:

```powershell
python scripts\run_due_platform_reviews.py --tenant-id 1 --list-only
python scripts\run_due_platform_reviews.py --tenant-id 1
```

Este runner es una pieza transitoria hasta conectar Redis/RQ o Celery; usa la misma proteccion que el endpoint `run-now`.

## Limites actuales

- e-coordina tiene mapeo confirmado de estados documentales agregados. 6conecta, CTAIMA, Nomio, Timenet, Validate y Vitaly CAE ya tienen conector read-only registrado, pero la sincronizacion fila a fila queda bloqueada hasta aprobar mapeos y resolucion de entidades por plataforma.
- El estado por plataforma refleja readiness local y contratos/mapeos; solo incorporara sincronizacion real cuando existan runs validos y mapeo documental estable.
- Los mapeos importados siguen pendientes hasta revision humana o confirmacion por proveedor.
- Las cuentas importadas siguen `proposal_disabled`, `dry_run=true` y `manual_approval_required=true`.
- Las revisiones programadas pueden ejecutarse con el runner local; falta llevarlas a worker RQ/Celery persistente.

## Siguiente paso recomendado

Crear una cola de "acciones preparables" por incidencia:

1. Resolver incidencia en el Hub.
2. Generar preview de cambios por plataforma.
3. Registrar auditoria previa.
4. Preparar exportacion manual o job RPA autorizado en `dry_run`.
5. Exigir aprobacion humana antes de cualquier escritura externa.
