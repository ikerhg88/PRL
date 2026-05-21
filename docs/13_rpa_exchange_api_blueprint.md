# 13 - API interna de intercambio por RPA autorizada

Fecha: 2026-05-18.

## Objetivo

Construir una API interna de IKER PRL/CAE Hub para intercambiar datos con plataformas externas que no ofrecen API propia, usando automatizacion de navegador autorizada contra formularios web.

La API no replica ni inventa endpoints del proveedor. Expone operaciones propias de IKER y ejecuta jobs RPA sobre cuentas autorizadas.

## Escritura interna y automatizacion externa

Cuando el operador pide escribir en la plataforma propia, se entiende el Hub IKER
PRL/CAE y sus datos locales. Esas escrituras internas se ejecutan en vivo si el
usuario tiene permisos, con validacion de tenant/empresa y auditoria normal del
backend. Ejemplos: crear trabajadores ARM, actualizar fichas, aprobar propuestas
OCR, corregir mapeos, registrar estados internos o generar paquetes de traslado.

La escritura en plataformas externas a las que ARM accede es un objetivo central
del proyecto: automatizar altas, cambios, subidas documentales y sincronizaciones
en los portales CAE autorizados. No debe tratarse como una excepcion ni como una
alternativa manual permanente.

Las restricciones de preview, `dry_run` inicial, prueba reversible, captcha/MFA
y aprobacion reforzada aplican para ejecutar esa automatizacion externa con
control y trazabilidad, no para impedirla. Una vez el flujo de una plataforma
este mapeado y autorizado, el job RPA/API debe poder escribir en vivo en la
plataforma externa correspondiente.

## Principio de alcance

El limite operativo no se define por botones concretos de la web, sino por datos y entidades autorizadas:

- Tenant autorizado.
- Empresa propia o gestionada autorizada.
- Trabajadores, maquinaria, vehiculos, centros, proyectos y documentos pertenecientes a esa empresa.
- Plataforma/cuenta externa asociada a esa empresa.
- Operacion de negocio permitida por contrato tecnico.

La RPA no debe actuar sobre empresas, trabajadores, centros o documentos fuera del alcance local autorizado aunque la sesion externa los muestre.

## Capas

1. API interna FastAPI.
2. Cola de jobs RPA.
3. Motor de navegador Playwright en modo normal.
4. Manifiesto de plataforma.
5. Auditoria append-only.
6. Evidencia minima redaccionada.

## Estado implementado 2026-05-18

La primera pieza operativa ya existe para lectura y prepara la base de escritura
externa:

- Schedules por plataforma: `/api/v1/platform-review-schedules`.
- Ejecucion manual protegida: `POST /api/v1/platform-review-schedules/{schedule_id}/run-now`.
- Historial de ejecuciones: `GET /api/v1/platform-review-schedules/{schedule_id}/runs`.
- Activacion segura cada 12 horas: `POST /api/v1/platform-review-schedules/activate-12h`.
- Estado operativo del modulo por plataforma: `GET /api/v1/platform-review-schedules/health`.
- Plan de variantes RPA por plataforma: `GET /api/v1/platform-review-schedules/rpa-variant-plan`.
- Runner local transitorio: `scripts/run_due_platform_reviews.py`.
- Conectores RPA ARM con lectura/captura inicial: e-coordina, 6conecta, CTAIMA, Nomio, Timenet, Validate y Vitaly CAE, bloqueados por flags y credenciales por entorno/local autorizado.
- Catalogo de traduccion: `scripts/build_platform_translation_catalog.py`.
- Catalogo operativo: `scripts/build_platform_operation_catalog.py`.

La lectura de estados reales ya esta confirmada en e-coordina para `Documentacion -> Solicitudes de documentacion`, columna `documentacion_estado`, con valores agregados redaccionados. El resto de conectores ARM queda al mismo nivel de arranque seguro: login/captura redaccionada y parada ante control humano. La siguiente capa es convertir esos mapeos en acciones de escritura externa auditadas por plataforma.

La activacion de 12 horas programa revisiones de estado en modo seguro: `dry_run=true`,
`manual_approval_required=true`. Las escrituras externas se ejecutan en jobs de
operacion especificos, no dentro de la revision periodica de lectura. El endpoint de salud separa
lo que funciona de lo que no:

- `working`: la plataforma esta programada cada 12 horas y la ultima lectura fue correcta.
- `not_working`: la ultima lectura fallo o quedo bloqueada por configuracion, credenciales o conector ausente.
- `not_checked`: esta programada pero aun no hay ejecucion.
- `not_configured`: no esta activa cada 12 horas.

## Rutas de escritura y preparacion

Actualizacion 2026-05-21:

- `GET /api/v1/exchange/write-matrix`: matriz interna por
  plataforma+empresa+cuenta y operacion. Devuelve si hay preview, dato local,
  mapeo, helper live especifico y bloqueos. No escribe en plataformas externas.
- `GET /api/v1/exchange/live-adapters`: inventario de conectores de escritura
  registrados, operaciones soportadas y requisito pendiente antes de live.
- `POST /api/v1/exchange/capture-write-screens/bulk`: crea pasarelas
  `capture_write_screen` para todas las cuentas/plataformas filtradas, evitando
  duplicar las que ya estan activas. No abre navegador ni escribe fuera; solo
  prepara el trabajo de mapeo editable.
- `POST /api/v1/exchange/workers/bulk-submit`: alta masiva de un trabajador en
  todas las cuentas con conector de escritura. En `dry_run=true` crea jobs de
  preparacion por cuenta; con `create_capture_requests=true` abre peticiones de
  pasarela para mapear lo que falte. En live solo avanza donde el preview este
  listo y el conector tenga helper especifico con lectura posterior.
- `POST /api/v1/exchange/{account_proposal_id}/preview`: preview de una
  operacion concreta con valores Hub redaccionados, cambios planificados y
  bloqueos.
- `POST /api/v1/exchange/{account_proposal_id}/submit`: submit interno por
  cuenta. Resuelve `platform_key` y conector desde el manifiesto/cuenta, registra
  auditoria, exige preview y delega en `/api/v1/transfers`. Si falta mapeo,
  dato local, aprobacion o helper live especifico, devuelve el bloqueo
  correspondiente en vez de inventar comportamiento externo.
- `POST /api/v1/exchange/{account_proposal_id}/capture-write-screen`: acceso
  corto para crear una pasarela humana `capture_write_screen` de mapeo editable
  sobre la cuenta seleccionada.

La matriz se implementa en `backend/app/services/platform_write_probe_matrix.py`
y es usada tambien por `scripts/probe_platform_write_previews.py`. Si una
plataforma tiene conector registrado pero no helper live especifico, el estado
de live debe ser `blocked_live_adapter_missing`; esto evita simular escrituras
o asumir selectores no validados.

## Pasarela humana de RPA asistida

Se incorpora una pasarela propia del Hub para operaciones que pueden encontrar captcha,
MFA, avisos legales o seleccion manual. La pasarela es visualmente distinta de la web
original del proveedor y actua como cockpit interno:

- API: `GET /api/v1/rpa-gateway/options`.
- API: `POST /api/v1/rpa-gateway/requests`.
- API: `GET /api/v1/rpa-gateway/requests`.
- API: `POST /api/v1/rpa-gateway/requests/{run_id}/decision`.
- API: `POST /api/v1/rpa-gateway/requests/{run_id}/launch-visible-browser`.
- API: `GET /api/v1/rpa-gateway/requests/{run_id}/browser-status`.
- API: `POST /api/v1/rpa-gateway/requests/{run_id}/sync-readonly-capture`.
- UI: `/rpa-gateway`.
- Smoke local sin terceros: `python scripts\smoke_rpa_gateway_captcha_demo.py`.

Funcionamiento actual:

1. El operador entra desde una accion de revision en `/platforms` o `/notifications`, o selecciona una plataforma en `/rpa-gateway`.
2. La UI genera un flujo guiado de `read_external_status`, registra auditoria y enfoca la peticion activa en `/rpa-gateway?request={id}`.
3. El mismo flujo registra la autorizacion humana antes de abrir nada externo.
4. Solo despues el backend lanza un navegador visible guiado con credenciales resueltas en memoria desde configuracion local/env. El helper usa un perfil local persistente segregado por tenant/plataforma/cuenta para conservar la sesion despues de la validacion humana; no exporta cookies, tokens, cuerpos HTTP ni HAR a evidencias. Usa Chromium de Playwright si esta instalado y, si falta, prueba Chrome o Microsoft Edge del sistema antes de devolver `browser_launch_failed`.
5. La pasarela consulta `browser-status` para mostrar si el asistente esta esperando login, captcha/MFA, credenciales enviadas, navegador abierto para el operador o lectura redaccionada disponible.
6. Si aparece un selector de empresa/cuenta, el asistente intenta seleccionar automaticamente solo cuando el contexto objetivo aprobado (`CLIENTE_A`, `CLIENTE_B`, etc.) produce una unica coincidencia visible. Si hay ambiguedad, captcha, MFA, aviso legal o sesion duplicada, el humano lo resuelve en pantalla sin bypass ni automatizacion de controles; el asistente espera a que desaparezca el control, continua con credenciales configuradas cuando proceda y conserva la sesion local para futuras aperturas de esa misma cuenta.
7. Si la plataforma permite continuar, el helper recoge una captura tecnica redaccionada de solo lectura: titulo, URL sin query, cabeceras, tarjetas, botones, enlaces, formularios, cabeceras de tabla, contadores de estados y senales objetivo. No guarda cookies, tokens, cuerpos HTTP, HTML, HAR, screenshots ni valores de filas personales.
8. El operador puede pulsar `Sincronizar lectura con Hub`; el backend guarda esa captura como evidencia `gateway.readonly_capture` en la ejecucion, registra auditoria y marca si hay bloqueos como sesion duplicada, captcha/MFA o falta de mapeo.
9. El Hub registra la decision humana, los pasos y los cambios externos realizados.
10. En una revision de estado `planned_external_changes=[]` y `changes_applied=[]`. Las escrituras externas se registran en jobs separados de operacion (`upsert_worker`, `upload_worker_document`, etc.) cuando el mapeo entre plataforma y entidades/documentos del Hub esta aprobado.

No se implementa resolucion automatica de captcha/MFA, proxy rotation, stealth ni
reintentos agresivos. Las acciones de escritura externa como `upsert_worker` o
`upload_worker_document` deben habilitarse por plataforma/cuenta cuando exista
preview, mapeo aprobado, entidad autorizada y aprobacion humana antes/despues.

El smoke local genera `artifacts/rpa-gateway/captcha_human_control_demo.html`, detecta
senales de captcha/MFA y recorre la pasarela hasta `human_control_resolved` con
`changes_applied=0` y `external_pages_contacted=false`.

Queda pendiente sustituir el runner local por Redis/RQ o Celery en servidor y
construir las pantallas de escritura externa para ejecutar altas/cambios/subidas
en plataformas reales con mapeos aprobados, entidad validada y prueba reversible
auditada.

## Adaptadores especificos por plataforma

El objetivo de producto es que el usuario vea una operacion simple, por ejemplo
`Revisar estado` o `Subir documento`, aunque por debajo cada plataforma requiera
un flujo distinto. Para conseguirlo no se debe crear un RPA generico que intente
adivinar pantallas: cada proveedor debe tener un adaptador propio, versionado y
probado, con variantes de login, seleccion de cuenta, navegacion y mapeo.

Cada adaptador de plataforma se compone de:

- `platform_profile`: nombre canonico, familia, hosts esperados, tenant/cuenta,
  limites operativos y capacidades disponibles.
- `login_methods`: lista ordenada de metodos de login soportados. Ejemplos de
  tipos: usuario/password en una pantalla, usuario primero y password despues,
  selector de empresa posterior al login, aviso legal intermedio, SSO/OIDC
  autorizado o sesion preexistente. Ningun metodo puede saltarse captcha/MFA.
- `account_context_methods`: reglas para confirmar que se esta dentro de la
  empresa correcta antes de leer o preparar cualquier accion. Si hay varias
  empresas visibles y no existe coincidencia aprobada, el flujo se detiene.
- `navigation_recipes`: pasos semanticos para llegar a areas de negocio como
  trabajadores, empresa, documentacion, incidencias o rechazos. Los pasos se
  validan por senales esperadas, no por confianza ciega en una URL.
- `read_mappings`: extraccion de estados, avisos, caducidades, pendientes y
  mensajes de rechazo hacia claves internas normalizadas.
- `write_mappings`: mapeos de campos y documentos usados solo para preview y
  futuras escrituras autorizadas. Deben estar aprobados y probados en dry-run
  antes de aparecer como accion disponible.
- `variant_rules`: variantes por version de portal, idioma, tenant, cuenta,
  cliente final o modulo contratado. La variante activa se elige por senales
  observadas y se registra en auditoria.
- `human_handoff`: puntos exactos donde el sistema debe pedir ayuda humana:
  captcha, MFA, aviso legal, sesion duplicada, selector ambiguo, datos fuera de
  alcance o pantalla inesperada.

El contrato de UX para el usuario es:

1. El Hub muestra una unica accion comprensible.
2. El backend selecciona el adaptador y la variante con mejor ajuste para esa
   plataforma/cuenta.
3. El operador ve objetivo, empresa, cuenta, host autorizado, estado del
   navegador y siguiente paso.
4. Las credenciales se resuelven en servidor y no se piden en pantalla.
5. Solo se interrumpe al humano cuando hay un control que debe resolver o una
   decision real que aprobar.
6. Cada paso explica que se esta leyendo o preparando y que se ha sincronizado
   en el Hub.

Reglas de calidad para dar de alta una variante:

- Debe provenir de captura tecnica redaccionada, documentacion oficial,
  contrato tecnico o prueba autorizada. No se aceptan selectores inventados.
- Debe tener prueba local o mock que cubra login, deteccion de control humano,
  seleccion de empresa, lectura y redaccion de evidencia.
- Debe declarar `dry_run_supported=true` y `manual_approval_required=true`.
- Debe declarar que datos puede leer, que datos puede escribir y que permisos
  exige. Si solo hay lectura, la UI no debe ofrecer escritura.
- Debe tener fallback a `manual_export` o `manual_followup_required` cuando la
  variante no encaje.
- Debe registrar la variante usada, senales de confianza, bloqueos y resultado
  en auditoria.

La persistencia automatica fila a fila en el Hub exige dos niveles de
confirmacion:

1. `capture_mapping_approved`: se sabe que columna/campo externo equivale a una
   clave interna (`worker.full_name`, `document.status`, `document.expires_at`,
   etc.).
2. `entity_resolution_approved`: se sabe que la fila externa corresponde a una
   entidad local concreta del tenant y empresa activa.

Sin esos dos niveles el sistema puede guardar evidencia redaccionada y contadores
agregados, pero no debe modificar estados de trabajadores/documentos locales.

Estado implementado 2026-05-19:

- API: `GET /api/v1/platform-review-schedules/rpa-variant-plan`.
- API: `GET /api/v1/platform-maps/data-coverage`.
- API: `GET /api/v1/platform-maps/edit-methods`.
- API: `POST /api/v1/exchange/{account_proposal_id}/preview`.
- UI: estrategia RPA iniciada desde `/platforms`, `/notifications` o `/rpa-gateway`.
- Alcance: todas las plataformas ARM importadas, no solo primera prioridad.
- Trazabilidad operativa: el frontend vigente trabaja por combinacion `plataforma + empresa externa + centro`, por ejemplo `CTAIMA / CTAIMA CAE / Empresa Demo Industrial, S.L. en CLIENTE_A`, no solo por plataforma.
- Mapa de datos: cada contexto declara cobertura para empresa, trabajadores, documentos, centros/proyectos, maquinaria/vehiculos y acceso/estados. El mapa separa claves observadas, propuestas por contrato y aprobadas; no guarda valores de filas externas.
- Mapa de edicion: cada contexto declara, campo a campo, si existe metodo de escritura listo para preview, si falta captura editable, si falta revision de mapeo o si el campo es solo lectura externa.
- Preview de escritura: cada cuenta externa puede generar un plan de escritura por operacion, entidad y campo, con valores locales redaccionados, bloqueos de mapeo, bloqueos de dato local y cambios externos planificados. Este preview no escribe fuera y registra auditoria `exchange.write_preview`.
- Registro backend de conectores de lectura: `e_coordina`, `seisconecta`, `ctaima`, `nomio`, `timenet`, `validate` y `vitaly_cae`.
- Registro backend de conectores de escritura RPA protegida:
  `connector_rpa_e_coordina_write`, `connector_rpa_seisconecta_write`,
  `connector_rpa_ctaima_write`, `connector_rpa_nomio_write`,
  `connector_rpa_timenet_write`, `connector_rpa_validate_write` y
  `connector_rpa_vitaly_cae_write`.
- Modulo comun `ConfiguredReadonlyConnector`: un unico envio de credenciales, navegador normal, no stealth, no proxy, sin descargas, sin cookies/HAR/cuerpos HTML, sin valores de filas y con evidencia redaccionada.
- Modulo comun `ConfiguredWriteConnector`: prepara operaciones de escritura en
  `dry_run` con auditoria y las bloquea sin escribir fuera hasta que existan
  contexto plataforma+empresa, mapeo aprobado, captura editable aprobada,
  preview, autorizacion humana y auditoria antes/despues.
- Perfil especifico 6conecta: `seisconecta/upsert_worker` usa los campos
  observados en el formulario real de alta (`worker.identifier_value`,
  `worker.first_name`, `worker.last_name`, `worker.nationality`,
  `worker.contract_type` y `worker.work_position`) para evitar bloqueos por
  campos genericos que no aparecen en esa pantalla.
- Escritura dummy autorizada 6conecta: el conector
  `connector_rpa_seisconecta_write` soporta `dry_run=false` solo con
  `account_proposal_id`, `manual_approval_required=true` y
  `live_external_write_authorized=true`. El helper usa navegador visible,
  sesion persistente, credenciales configuradas y el formulario capturado
  `trabajador.apply`; si aparece captcha/MFA se detiene para control humano.
- La pasarela humana acepta `capture_write_screen` para abrir una pantalla editable
  autorizada, capturar estructura redaccionada y desbloquear mapeos. Esta accion
  no guarda cambios ni sube ficheros.
- Helper visible `readonly_capture_v8_persistent_session`: perfil local persistente por cuenta, reutilizacion de sesion despues de captcha/MFA resuelto por humano y estado UI con `session_persistence` redaccionado.
- Seleccion automatica segura de contexto: el helper recibe `target_context` desde la pasarela y puede abrir/selectar un desplegable de empresa solo si encuentra una coincidencia unica; ante varias opciones o pantalla no reconocida pasa a `human_context_required`.
- Lee el snapshot local de ARM: empresa, trabajadores, intakes pendientes,
  registros de plataforma y estados externos persistidos.
- Enumera variantes candidatas por plataforma: `single_page_password`,
  `two_step_password`, `existing_session_or_resume`, `human_control_handoff`,
  confirmacion de empresa/cuenta, captura redaccionada, mapeo fila a fila y
  fallback manual.
- Politica obligatoria: un unico envio de credenciales por cuenta y ejecucion,
  sin intentos paralelos, sin selector guessing y parada ante captcha, MFA,
  aviso legal, sesion duplicada, rate limit, empresa inesperada o pantalla sin
  variante aprobada.

## Mapa completo de datos por plataforma y empresa

El contrato operativo actual se materializa en `GET /api/v1/platform-maps/data-coverage`
y en el script:

```powershell
python scripts\build_platform_data_mapping.py --tenant-id 1 --priority-group all
```

El resultado se guarda en `artifacts/platform-data-mapping/`:

- `platform_data_mapping.redacted.json`: cobertura completa por contexto.
- `platform_data_mapping_coverage.redacted.csv`: matriz plana por categoria.
- `platform_data_mapping_pending.redacted.csv`: lista estructurada de pendientes
  para el GUI, con severidad, categoria, clave canonica y accion sugerida.
- `platform_data_mapping_summary.redacted.md`: resumen humano.

El mapa no significa que se hayan extraido todos los valores externos. Significa
que el Hub sabe, para cada plataforma+empresa externa, que claves internas son
necesarias, cuales tienen equivalencia observada/propuesta, cuales estan
aprobadas y cuales faltan para poder leer y persistir filas con seguridad. Las
categorias cubiertas son empresa, trabajadores, documentos, centros/proyectos,
maquinaria/vehiculos y acceso/estados.

Cada contexto expone `pending_items` y `pending_summary`. Estos objetos son la
cola que debe consumir el GUI: `account_not_active`, `host_pending`,
`entry_url_missing`, `missing_required_key` y `pending_mapping_review`.

## Mapa de metodos de edicion por campo

El contrato de escritura campo a campo se materializa en
`GET /api/v1/platform-maps/edit-methods` y en el script:

```powershell
python scripts\build_platform_field_edit_methods.py --tenant-id 1 --priority-group all
```

El resultado se guarda en `artifacts/platform-edit-methods/`:

- `platform_field_edit_methods.redacted.json`: catalogo completo por
  plataforma+empresa y campo canonico.
- `platform_field_edit_methods.redacted.csv`: matriz plana de campo, metodo,
  estado, evidencia y accion siguiente.
- `platform_edit_operations.redacted.csv`: operaciones de negocio y campos
  requeridos para `upsert_worker`, subidas documentales, bajas y sincronizacion
  de empresa.
- `platform_field_edit_summary.redacted.md`: resumen humano.

Los estados de campo son:

- `ready_for_preview`: hay evidencia editable observada; el job puede preparar
  un preview con datos ARM y auditoria antes/despues.
- `needs_editable_capture`: el mapeo existe, pero falta captura de pantalla
  editable autorizada.
- `needs_mapping_review`: hay etiqueta o mapeo candidato, pero falta
  confirmacion antes de escribir.
- `needs_mapping`: falta equivalencia para ese campo.
- `not_external_edit_target`: el campo se lee desde la plataforma, pero no se
  edita desde el Hub.
- `credential_secret_only`: el valor procede del almacen cifrado de credenciales
  y nunca se pide ni se registra al operador.

Los metodos no guardan selectores comerciales inventados. La estrategia es
resolver en ejecucion por etiqueta observada o nombre estable ya capturado, con
preview, autorizacion humana y auditoria para cada escritura externa.

## Preview de escritura por cuenta

El endpoint:

```http
POST /api/v1/exchange/{account_proposal_id}/preview
```

recibe:

- `operation`: `sync_company_profile`, `upsert_worker`, `deactivate_worker`,
  `upload_worker_document`, `upload_company_document` o
  `upload_machine_vehicle_document`.
- `company_id`, `worker_id` y/o `document_version_id` segun la operacion.

Devuelve:

- Estado global: `preview_ready`, `blocked_mapping_review_required` o
  `blocked_local_data_required`.
- Contexto plataforma+empresa externa.
- Entidad local origen.
- Campo por campo: metodo, estado de mapeo, valor Hub redaccionado, bloqueos y
  siguiente accion.
- `planned_external_changes` solo cuando el campo es enviable.
- Politica segura: `external_write_enabled=false`, `dry_run_required=true`,
  `manual_approval_required=true` y auditoria antes/despues obligatoria.

Este preview es el puente entre mapeo y escritura. No ejecuta RPA live. Si el
preview queda bloqueado por mapeo, la UI ofrece `Capturar editable`, que crea una
peticion `capture_write_screen` en la pasarela humana. El operador navega hasta
la pantalla de edicion, no guarda cambios, y luego sincroniza la captura
redaccionada al Hub para revisar/aprobar los campos reales.

Cuando una cuenta dummy autorizada ya tiene preview listo y mapeo aprobado, la
ejecucion live se canaliza por `POST /api/v1/transfers` con
`dry_run=false`, `manual_approval_required=true`,
`live_external_write_authorized=true` y `account_proposal_id`. El primer caso
operativo es `connector_rpa_seisconecta_write/upsert_worker` para la cuenta
`VELARTIA IGORRE / CONGELADOS DENAVARRA`: usa el helper
`scripts/seisconecta_live_upsert_worker.py`, credenciales configuradas,
navegador visible con perfil persistente por cuenta, formulario capturado
`task=trabajador.apply` y evidencia redaccionada en
`artifacts/external-writes/seisconecta/`. El helper no resuelve captcha/MFA ni
oculta automatizacion; si aparece control humano se detiene y espera al operador.

Regla vigente desde 2026-05-20: ninguna escritura externa se considera valida
solo por haber ejecutado el submit. El conector debe hacer una lectura posterior
en la plataforma y confirmar la evidencia de la accion. Los estados son:

- `submitted_external_pending_readback`: el submit se ejecuto, pero la lectura
  posterior no ha confirmado aun la accion. El operador ve que hubo accion, pero
  el Hub no la marca como valida.
- `confirmed_external`: el submit se ejecuto y una lectura posterior encontro
  senales suficientes de la entidad/documento creado o actualizado.

La primera prueba live dummy autorizada de 6conecta dejo evidencia de submit en
`artifacts/external-writes/seisconecta/upsert-worker-31-20260520-063612.status.json`.
La lectura posterior quedo no confirmada en
`artifacts/external-writes/seisconecta/readback-worker-31-20260520-v3.status.json`.
Por tanto el transfer local queda en `submitted_external_pending_readback` y el
registro de plataforma del trabajador en `submitted_pending_readback`.

## Superficies de validacion posterior

Para detectar acciones que quedan pendientes de validador humano, notificacion,
rechazo o incidencia, se anade el mapa:

```http
GET /api/v1/platform-maps/validation-surfaces
```

y el script:

```powershell
python scripts\build_platform_validation_surface_map.py
```

Los artefactos se guardan en `artifacts/platform-validation-surfaces/` y sirven
como plan de lectura posterior por plataforma. La ejecucion local ARM encontro
129 superficies en 7 plataformas actuales. Las plataformas con evidencia mas
usable para readback son 6conecta, e-coordina, Nomio y Timenet. Validate,
Vitaly CAE y especialmente CTAIMA necesitan una captura interna mas profunda
posterior a seleccion de empresa/cliente antes de afirmar que sus bandejas de
pendientes, notificaciones o rechazos estan mapeadas.

Documento: `docs/27_platform_validation_surfaces.md`.

## Informe de datos obtenidos y correspondencias

Para revision administrativa y tecnica de que se ha obtenido de cada plataforma
y que campo externo corresponde con cada campo interno existe el script:

```powershell
python scripts\build_platform_obtained_data_mapping_report.py --tenant-id 1
```

El resultado se guarda en `artifacts/platform-obtained-mapping/`:

- `platform_obtained_data_mapping_latest.pdf`: informe principal.
- `platform_obtained_data_mapping_latest.html`: version navegable.
- `platform_obtained_data_mapping_latest.json`: payload estructurado.
- `platform_obtained_data_index.redacted.csv`: indice de capturas por
  plataforma/contexto.
- `platform_field_correspondences.redacted.csv`: correspondencias
  campo/etiqueta externa -> clave interna.
- `platform_field_correspondences_mapped.redacted.csv`: solo filas con clave
  interna detectada o mapeada.
- `platform_external_statuses.redacted.csv`: estados documentales externos
  persistidos cuando existan.

Este informe no declara capacidades ni readiness. Se limita a contextos,
capturas redaccionadas, etiquetas visibles, observaciones registradas y
correspondencias de campos.

## Fase previa: mapa estructural

Antes de construir un manifiesto RPA por proveedor se debe crear o importar un snapshot estructural en `/api/v1/platform-maps/snapshots` y revisar sus etiquetas en `/api/v1/platform-maps/labels`.

El manifiesto de intercambio no debe depender de etiquetas descubiertas sin revisar. Para operaciones de escritura se usaran solamente mapeos aprobados, vinculados al tenant, empresa, cuenta externa y operacion autorizada.

Documento de referencia: `docs/16_platform_structure_mapping_system.md`.

## Endpoints internos propuestos

Todos requieren autenticacion, tenant y permiso `connector.execute` o `connector.approve` segun fase.

### Preview

```http
POST /api/v1/exchange/{platform_account_id}/workers/preview
POST /api/v1/exchange/{platform_account_id}/documents/preview
POST /api/v1/exchange/{platform_account_id}/company/preview
```

Salida:

- Job id.
- Entidades candidatas.
- Datos locales a enviar.
- Campos externos esperados.
- Riesgos o datos incompletos.
- `dry_run=true`.

### Submit

```http
POST /api/v1/exchange/{platform_account_id}/workers/submit
POST /api/v1/exchange/{platform_account_id}/documents/submit
POST /api/v1/exchange/{platform_account_id}/company/submit
```

Entrada:

- `preview_job_id`.
- `approval_comment`.
- Lista exacta de entidades aprobadas.

Salida:

- Job id de ejecucion.
- Estado inicial.
- Requiere navegador asistido si aparece captcha, MFA o seleccion manual.

### Estado

```http
GET /api/v1/exchange/jobs/{job_id}
GET /api/v1/exchange/jobs/{job_id}/attempts
GET /api/v1/exchange/jobs/{job_id}/evidence
```

## Modelo de job

Estados:

- `draft`.
- `preview_running`.
- `preview_ready`.
- `approval_required`.
- `approved`.
- `running`.
- `human_action_required`.
- `completed`.
- `completed_with_warnings`.
- `failed`.
- `cancelled`.

Cada job guarda:

- Tenant.
- Empresa local.
- Cuenta de plataforma.
- Operacion.
- `dry_run`.
- `manual_approval_required`.
- Entidades locales incluidas.
- Resultado por entidad.
- Hash de documentos enviados.
- Evidencia minima.
- Usuario aprobador.

## Operaciones de negocio

El manifiesto de cada plataforma debe mapear operaciones, no botones:

- `sync_company_profile`.
- `upsert_worker`.
- `deactivate_worker`.
- `upload_worker_document`.
- `upload_company_document`.
- `read_external_status`.
- `read_rejections`.
- `download_receipt`.

Cada operacion define:

- Entidad local origen.
- Campos requeridos.
- Reglas de validacion.
- Pantallas o pasos esperados.
- Confirmacion final.
- Estado externo esperado.
- Evidencia minima.

## RPA asistida

Cuando el proveedor use captcha, MFA, seleccion de cliente, aviso legal o cualquier paso no determinista:

- El job pasa a `human_action_required`.
- El operador autorizado resuelve el paso en navegador visible.
- El sistema continua solo si la sesion vuelve a una pagina esperada del manifiesto.
- No se automatiza la resolucion del control.
- No se usan proxies rotatorios, stealth, spoofing ni servicios de resolucion de captcha.
- Si el control aparece durante una escritura, el job queda suspendido antes de cualquier confirmacion final.

## Verificacion reversible de escritura

Antes de declarar que una plataforma soporta escrituras externas, debe pasar una prueba controlada:

1. Usar entidad dummy o sandbox del proveedor.
2. Seleccionar un campo no sensible y reversible.
3. Capturar estado `before` redaccionado.
4. Cambiar un unico valor.
5. Guardar solo tras aprobacion manual.
6. Verificar el cambio con evidencia minima.
7. Restaurar inmediatamente el valor original.
8. Verificar restauracion.
9. Registrar auditoria antes/despues y resultado.

Esta prueba esta catalogada en `docs/24_platform_operation_catalog.md`, pero no se ha ejecutado contra plataformas comerciales.

## Controles de datos

Antes de enviar:

- Validar que cada entidad pertenece al tenant.
- Validar que pertenece a la empresa autorizada de la cuenta externa.
- Validar permisos del usuario aprobador.
- Validar que el tipo documental esta permitido para esa plataforma.
- Validar que no hay datos medicos no permitidos.
- Validar que el documento tiene SHA-256 y version inmutable.

Despues de enviar:

- Guardar resultado por entidad.
- Guardar identificador externo solo si aparece en respuesta o UI de forma estable.
- Guardar estado externo y fecha.
- Guardar evidencia minima sin secretos.

## Evidencia minima

Permitido:

- Nombre de operacion.
- Entidad local.
- Plataforma.
- Timestamp.
- Estado externo.
- Hash de documento.
- Mensajes de error redaccionados.
- Captura opcional solo si no contiene datos personales excesivos.

No permitido:

- Passwords.
- Cookies.
- Tokens.
- Cuerpos HTTP completos.
- HAR.
- Datos de otras empresas.
- Historial medico o diagnosticos.

## Primeras plataformas candidatas ARM

Por captura previa:

- `e-coordina`: varias cuentas ARM con acceso probable.
- `Validate`: acceso probable.
- `6conecta`: acceso probable.
- `Timenet`: acceso probable.
- `Nomio`: acceso probable, pero contiene datos laborales sensibles; tratar con mayor minimizacion.

CTAIMA/Metacontratas requieren modo asistido o via acordada con proveedor cuando aparece captcha/control.
