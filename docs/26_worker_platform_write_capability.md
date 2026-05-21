# 26 - Capacidad de escritura de trabajadores en plataformas

Fecha: 2026-05-20.

## Objetivo operativo

El objetivo de producto es que el alta o actualizacion de un trabajador en el
Hub pueda generar, para cada plataforma+empresa habilitada, una operacion guiada
que cree o actualice la ficha externa con toda la informacion necesaria:

- Identidad: nombre, apellidos, DNI/NIE y caducidad si aplica.
- Datos laborales: puesto, contrato, centro/proyecto, alta/baja.
- Contacto: email y telefono cuando la plataforma los exige.
- Seguridad social: NAF/NUSS solo si esta autorizado y requerido.
- Aptitud medica: solo aptitud, restricciones preventivas si aplica,
  emision/caducidad y evidencia minima; nunca historial medico.
- Documentacion de trabajador: tipo documental, fichero, SHA-256,
  emision/caducidad y estado posterior leido desde la plataforma.

La escritura externa debe seguir siendo auditada, con preview previo,
aprobacion humana y parada ante captcha/MFA o pantalla inesperada.

## Estado real actual

Hay siete conectores RPA de escritura registrados:

- `connector_rpa_e_coordina_write`
- `connector_rpa_seisconecta_write`
- `connector_rpa_ctaima_write`
- `connector_rpa_nomio_write`
- `connector_rpa_timenet_write`
- `connector_rpa_validate_write`
- `connector_rpa_vitaly_cae_write`

Solo `connector_rpa_seisconecta_write` tiene escritura live validada en cuenta
dummy autorizada, para la operacion `upsert_worker`. Desde 2026-05-20 una
escritura solo se considera valida cuando la lectura posterior confirma al
trabajador en la plataforma.

## Matriz actual por plataforma

| Plataforma | Cuenta(s) ARM | Alta/edicion trabajador | Campos que puede enviar ahora | Estado |
| --- | --- | --- | --- | --- |
| 6conecta | VELARTIA IGORRE / CONGELADOS DENAVARRA | Live submit validado | DNI/NIE, nombre, apellidos, nacionalidad, contrato, puesto | `confirmed_external`: accion ejecutada y lectura posterior confirmada |
| e-coordina | 6 cuentas ARM | Preview/dry-run parcial | Nombre detectado; faltan identificador, apellidos y resto de campos | No escribe live |
| CTAIMA / CTAIMA CAE | 3 cuentas ARM | Preview/dry-run bloqueado | Sin campos de trabajador listos para preview | No escribe live |
| Nomio | NOMIO | Preview/dry-run bloqueado | Sin campos de trabajador listos para preview | No escribe live |
| Timenet | TIMENET | Preview/dry-run bloqueado | Sin campos de trabajador listos para preview | No escribe live |
| Validate | ARKAL/NEMAK/FLORETTE | Preview/dry-run bloqueado | Sin campos de trabajador listos para preview | No escribe live |
| Vitaly CAE | SEDA | Preview/dry-run bloqueado | Sin campos de trabajador listos para preview | No escribe live |

## Aplicacion del mismo metodo a todas las plataformas

Actualizacion 2026-05-21:

- Todos los conectores RPA de escritura registrados aceptan el mismo contrato de
  seguridad: `dry_run`, `manual_approval_required`, preview previo, auditoria,
  parada ante captcha/MFA y sin credenciales en logs.
- Las plataformas que aun no tienen helper live especifico devuelven
  `blocked_live_adapter_missing` si alguien intenta `dry_run=false`. Ese estado
  exige `platform_specific_live_adapter`, lectura previa anti-duplicado, submit
  autorizado y lectura posterior confirmada antes de permitir escritura real.
- Se regenero la matriz global:
  `artifacts/platform-write-probes/platform_write_probe_20260521-063747.{json,csv,md}`.
- Resultado de la matriz: 20 plataformas, 34 contextos plataforma+empresa,
  238 operaciones evaluadas, 1 fila `preview_ready`, 169 bloqueos por mapeo y
  68 operaciones saltadas por falta de version documental compatible.
- Estado de helper live en esa matriz: 7 filas con helper especifico disponible
  (6conecta), 91 filas bloqueadas por falta de helper especifico y 140 filas
  sin conector de escritura registrado.
- La unica fila lista sigue siendo `6conecta / VELARTIA IGORRE / CONGELADOS
  DENAVARRA / upsert_worker`. No se ejecuto ninguna escritura externa durante
  la matriz (`external_writes_executed=0`).
- Por tanto, no hay base tecnica segura para repetir escrituras live en CTAIMA,
  e-coordina, Nomio, Timenet, Validate, Vitaly CAE ni el resto de plataformas
  hasta capturar/aprobar sus pantallas editables y mapas de lectura posterior.

Actualizacion de rutas 2026-05-21:

- La matriz ya no vive solo en `scripts/`: se extrajo a
  `backend/app/services/platform_write_probe_matrix.py` para que API, jobs,
  pruebas y scripts usen el mismo criterio.
- Nuevas rutas internas:
  - `GET /api/v1/exchange/write-matrix`: devuelve readiness por
    cuenta+operacion, estado de mapeo, dato local, helper live y dry-run de
    conector sin ejecutar escrituras externas.
  - `GET /api/v1/exchange/live-adapters`: enumera conectores registrados,
    operaciones soportadas y si existe helper live especifico o queda
    `blocked_live_adapter_missing`.
  - `POST /api/v1/exchange/capture-write-screens/bulk`: crea pasarelas de
    captura editable para todas las cuentas/plataformas, incluidas las que aun
    no tienen conector de escritura registrado, sin duplicar las activas.
  - `POST /api/v1/exchange/workers/bulk-submit`: prepara el alta de un
    trabajador en todas las cuentas con conector, crea jobs dry-run y puede abrir
    automaticamente peticiones `capture_write_screen` para mapear lo pendiente.
  - `POST /api/v1/exchange/{account_proposal_id}/submit`: ruta de submit por
    cuenta que resuelve plataforma y conector automaticamente y usa el circuito
    auditado de transferencias.
  - `POST /api/v1/exchange/{account_proposal_id}/capture-write-screen`: crea
    una peticion de pasarela humana `capture_write_screen` para capturar pantalla
    editable redaccionada sin guardar cambios ni subir ficheros.
- Skill local creado y validado:
  `C:/Users/ikerh/.codex/skills/iprl-cae-platform-write-method`. Resume el
  metodo obligatorio para nuevas rutas/adaptadores de escritura.

Prueba operativa 2026-05-21:

- Endpoint usado: `POST /api/v1/exchange/workers/bulk-submit`.
- Trabajador: `#19 Prueba Hub Escritura Final`.
- Resultado: 14 cuentas con conector evaluadas.
- 6conecta: transfer `#34`, `dry_run=false`, estado
  `already_exists_external`; el Hub no repitio el alta porque la lectura
  confirmo que ya existia en la cuenta externa.
- Registro local: `WorkerPlatformRegistration #5`, estado `confirmed`,
  `platform_account_id=8`.
- Resto de cuentas: 13 peticiones `capture_write_screen` creadas para mapear
  pantallas editables antes de escribir: runs `#12` a `#24`.

Prueba Alicia 2026-05-21:

- Trabajador: `#11 Alicia Gomez`.
- Estado local: faltan datos ARM obligatorios para alta en plataformas
  (`identifier_value`, nacionalidad, contrato, puesto, contacto y otros campos
  segun proveedor).
- Resultado por cuentas con conector:
  - CTAIMA/CLIENTE_A: `already_exists_external`; no se puede dar de alta porque ya
    existe en esa cuenta, estado actual `missing_required_document`.
  - 6conecta: `blocked_submit` por `blocked_local_data_required`.
  - CTAIMA no Cliente A, e-coordina, Nomio, Timenet, Validate y Vitaly:
    `blocked_submit` por mapeo/helper live pendiente.
- Pasarelas creadas: runs `#25` a `#37` para captura editable y mapeo.

Pasarelas globales 2026-05-21:

- Endpoint usado: `POST /api/v1/exchange/capture-write-screens/bulk`.
- Resultado en base local ARM: 34 cuentas evaluadas, 20 pasarelas nuevas
  creadas y 14 omitidas por existir ya una pasarela activa.
- Nuevas pasarelas: runs `#38` a `#57`.
- Cubre cuentas sin conector de escritura registrado como Dokyfy, Folyo,
  IEDOCE, Integra ASEM, Koordinatu, Metacontratas, Quioo, Quironprevencion,
  SGS Gestiona, Sarenet, SmartOSH, UCAE y eGestiona.

## Evidencia 6conecta

La prueba dummy autorizada de 6conecta queda trazada en:

- Transfer local: `#14`, estado `submitted_external_pending_readback`, `dry_run=false`.
- Trabajador local: `#31 Prueba Live Seisconecta 60535`.
- Registro local de plataforma: `submitted_pending_readback`, origen
  `connector_rpa_seisconecta_write`.
- Evidencia redaccionada:
  `artifacts/external-writes/seisconecta/upsert-worker-31-20260520-063612.status.json`.
- Evidencia de lectura posterior:
  `artifacts/external-writes/seisconecta/readback-worker-31-20260520-v3.status.json`.

Ese estado significa que el submit externo se ejecuto, pero la lectura posterior
no encontro senales suficientes del trabajador en las vistas visibles. Por tanto
el Hub informa la accion al operador, pero no la marca como escritura validada.

Actualizacion posterior del 2026-05-20:

- Trabajador local: `#23 Prueba Hub Autorizada No Usar`.
- Cuenta externa ARM: propuesta `#8`, plataforma/cuenta `#8`,
  `VELARTIA IGORRE / CONGELADOS DENAVARRA`.
- Transfers live: `#25` y `#26`, ambos `dry_run=false`, estado
  `submitted_external_pending_readback`.
- Evidencias:
  `artifacts/external-writes/seisconecta/upsert-worker-23-20260520-201848.status.json`,
  `artifacts/external-writes/seisconecta/readback-worker-23-20260520-202345.status.json`
  y `artifacts/external-writes/seisconecta/upsert-worker-23-20260520-202654.status.json`.
- Resultado: se ejecuto el submit externo, pero la lectura posterior no confirmo
  el alta. Por tanto sigue sin ser una escritura valida segun la regla del Hub.
- Se corrigio el bloqueo de duplicados para que un registro historico sin
  `platform_account_id` tambien bloquee nuevos `upsert_worker` sobre la misma
  plataforma/cuenta. Los jobs y el registro local de esta prueba quedaron
  normalizados contra `platform_account_id=8`.

Actualizacion final del 2026-05-20:

- El helper de 6conecta ya hace lectura previa. Si el trabajador ya aparece en
  la plataforma, devuelve `already_exists_external`, no ejecuta otra alta y el
  Hub crea/actualiza el registro local como `confirmed`.
- Se corrigio el envio real: el boton visible y habilitado de 6conecta se invoca
  mediante el propio manejador de la pagina, manteniendo validaciones cliente;
  no se usa `requestSubmit` ni endpoints inventados.
- Si no se observa una URL de submit pero la lectura posterior confirma un
  trabajador que no estaba en la lectura previa, el job se marca como
  `confirmed_external`.
- Transfer validado desde el Hub: `#33`, trabajador local `#20 Prueba Hub
  Confirmada Lectura`, `dry_run=false`, `post_write_read_confirmed=true`,
  `valid_external_write=true`, evidencia
  `artifacts/external-writes/seisconecta/upsert-worker-20-20260520-213914.status.json`.
- Transfer anti-duplicado validado desde el Hub: `#31`, trabajador local `#18`,
  estado `already_exists_external`, lectura positiva y sin repetir alta.

Actualizacion 2026-05-21:

- Nueva escritura live validada contra `6conecta`:
  - Trabajador local `#26 Prueba Hub Lote Escritura 20260521`.
  - Transfer `#35`, estado `confirmed_external`.
  - `dry_run=false`, `manual_approval_required=true`,
    `post_write_read_confirmed=true`, `valid_external_write=true`.
  - Registro local `WorkerPlatformRegistration #6`, `platform_account_id=8`,
    `external_worker_id=5710689`.
- Cobertura live actual:
  - Escritura real confirmada: `6conecta` (`upsert_worker`).
  - Escritura bloqueada por falta de helper/mapeo live aprobado:
    CTAIMA, e-coordina, Nomio, Timenet, Validate y Vitaly CAE.
  - Sin conector de escritura registrado todavia: Dokyfy, Folyo, IEDOCE,
    Integra ASEM, Koordinatu, Metacontratas, Quioo, SGS Gestiona, SmartOSH,
    UCAE y eGestiona.
  - Configuracion incompleta: Quironprevencion y Sarenet tienen
    `PENDIENTE_URL/PENDIENTE_HOST`.
- Pasarelas `capture_write_screen` lanzadas para mapeo por
  plataforma+empresa/centro. Las capturas sincronizadas se usan solo como
  evidencia/mapeo; no habilitan escritura hasta aprobar campos editables,
  preview, aprobacion humana, auditoria y lectura posterior.

## Brecha para "toda la informacion"

El modelo local de trabajador ya contiene mas campos de los que 6conecta envia
actualmente:

- `identifier_expires_at`
- `social_security_number`
- `email`
- `phone`
- `starts_at`
- `ends_at`
- `work_center_name`
- `risk_profile`
- `medical_fitness_status`
- `medical_fitness_issued_at`
- `medical_fitness_expires_at`
- `medical_fitness_provider`
- `medical_fitness_restrictions`
- `cae_notes`

Para cumplir el objetivo completo hacen falta dos capas:

1. En cada plataforma, capturar y aprobar la pantalla editable real para los
   campos que su formulario permita editar. Si la plataforma no tiene un campo
   en el alta de trabajador, se debe enviar en una operacion posterior o marcar
   como no aplicable.
2. En el Hub, convertir el alta de trabajador en una orquestacion: tras guardar
   la ficha local, generar previews por plataforma+empresa habilitada,
   mostrar bloqueos/campos faltantes, pedir aprobacion y ejecutar los jobs live
   disponibles.

## Confirmacion para el operador

La API de transferencias expone, por cada job, el ultimo mensaje del intento y
los flags:

- `post_write_read_confirmed`: indica si hubo lectura posterior positiva.
- `valid_external_write`: solo es `true` cuando la accion externa fue ejecutada
  y confirmada por lectura posterior.
- `status_artifact`: apunta a la evidencia redaccionada mas relevante, dando
  prioridad al artefacto de lectura posterior cuando la confirmacion falla.

La pantalla `/transfers` muestra esos datos bajo el resultado para que el
operador distinga entre accion ejecutada, pendiente de confirmacion y accion
validada.

## Siguiente orden tecnico

1. Completar `6conecta/upload_worker_document`, porque el alta de trabajador sin
   documentos no resuelve el flujo CAE completo.
2. Capturar pantalla editable de trabajador en CTAIMA/CLIENTE_A y mapear
   `upsert_worker` con la misma profundidad que 6conecta.
3. Repetir por e-coordina, Validate, Vitaly CAE, Timenet y Nomio.
4. Anadir en `/workers` un panel de "Publicacion en plataformas" que desde una
   ficha de trabajador genere previews, lance jobs y muestre el estado por
   plataforma+empresa.

## Actualizacion 2026-05-21 10:09

- Se anadio `scripts/launch_platform_capture_flows.py` para crear, autorizar,
  lanzar y sincronizar pasarelas `capture_write_screen` de cuentas activas sin
  ejecutar escrituras externas.
- Se corrigio que los scripts de reporte no vuelvan a ejecutar el seed por
  defecto, para no pisar la configuracion vigente importada desde
  `usuarios y contraseñas PLATAFORMAS.xlsx`.
- Se considera `proposal_disabled` como estado inactivo para matrices
  operativas.
- Se resincronizo el Excel vigente: 30 cuentas activas y 4 cuentas baja.
- Ejecucion de accesos guiados:
  `artifacts/platform-access-launches/platform_access_launch_20260521_100900.md`.
  Resultado: 30 cuentas objetivo, 30 navegadores ya lanzados, 22 capturas
  sincronizadas, 8 pendientes de intervencion/login/contexto, 0 escrituras
  externas.
- Las capturas sincronizadas generan propuestas de mapeo `field` en
  `pending_review` cuando la etiqueta observada se puede asociar a una clave
  estandar del Hub. No se autoaprueban mapeos ni selectores.
- Matriz vigente de alta de trabajador:
  `artifacts/platform-write-readiness/current_platform_write_readiness_20260521_100909.md`.
  Resultado: 30 contextos activos, 0 altas reales inmediatas, 1 helper live
  especifico (`6conecta`), 11 bloqueados por helper/mapeo pendiente y 18 sin
  conector de escritura registrado.
