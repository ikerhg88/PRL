# 24 - Catalogo operativo de plataformas

Fecha: 2026-05-18.

## Objetivo

Catalogar que operaciones ejecutara el Hub IKER PRL/CAE por plataforma para automatizar procesos externos: altas, actualizaciones, subidas documentales, bajas, lecturas de estado, rechazos y recibos.

Este catalogo no es un reporte de datos obtenidos. Sirve para saber que falta antes de ejecutar escrituras reales en plataformas externas con autorizacion, mapeos aprobados, preview, aprobacion humana y auditoria antes/despues.

## Politica de escritura en vivo

Las escrituras dentro de la plataforma propia, el Hub IKER PRL/CAE, son
operaciones internas y pueden ejecutarse en vivo cuando el usuario lo solicita y
el permiso local lo permite. Deben quedar auditadas, pero no necesitan buscar una
alternativa `dry_run` si el objetivo es corregir datos del Hub.

Las escrituras hacia plataformas comerciales externas son el objetivo operativo
del modulo. Deben ejecutarse desde jobs especificos cuando existan autorizacion,
mapeos aprobados, preview, `dry_run` inicial, aprobacion humana y auditoria
antes/despues.

## Comando

```powershell
python scripts\build_platform_operation_catalog.py
python scripts\build_platform_field_edit_methods.py --tenant-id 1 --priority-group all
```

## Artefactos

Carpeta:

```text
artifacts/platform-operations/
```

Archivos:

- `platform_operation_catalog.redacted.json`: catalogo operativo completo.
- `platform_operation_readiness.redacted.csv`: matriz por plataforma y operacion.
- `platform_captcha_support.redacted.csv`: soporte captcha/MFA por plataforma.
- `platform_operation_summary.redacted.md`: resumen humano.

Carpeta de metodos de edicion campo a campo:

```text
artifacts/platform-edit-methods/
```

Archivos:

- `platform_field_edit_methods.redacted.json`: catalogo por plataforma+empresa y campo canonico.
- `platform_field_edit_methods.redacted.csv`: matriz plana de metodo de edicion por campo.
- `platform_edit_operations.redacted.csv`: operaciones de escritura y campos requeridos.
- `platform_field_edit_summary.redacted.md`: resumen humano.

## Resultado

- Plataformas catalogadas: 53.
- Entradas de operacion: 423.
- Operaciones de escritura verificadas con guardado externo: 0.
- Operaciones de escritura catalogadas solo como plan/dry-run: 282.
- Plataformas con politica captcha/MFA asistida o control humano: 47.

Lectura real confirmada:

- `e_coordina` -> `read_external_status` con valores agregados reales desde `documentacion_estado`.

## Captcha/MFA

El soporte permitido es:

1. Detectar captcha, MFA, aviso legal, seleccion manual o control no determinista.
2. Pasar el job a `human_action_required`.
3. Mostrar navegador normal al operador autorizado.
4. Continuar solo si la sesion vuelve a una pagina esperada del manifiesto.
5. Registrar evidencia minima redaccionada.

No se soporta ni se implementara:

- Resolucion automatica de captcha.
- Bypass de MFA.
- Proxy rotation, stealth o user-agent spoofing enganoso.
- Reintentos agresivos que puedan bloquear cuentas.

## Prueba reversible de escritura

La prueba propuesta por el usuario, cambiar un campo, guardar y devolverlo a su valor original, queda catalogada pero no ejecutada.

Condiciones obligatorias antes de hacerla:

1. Entidad dummy o sandbox del proveedor; no usar datos reales de trabajadores salvo autorizacion concreta.
2. Mapeo aprobado de la pantalla y del campo exacto.
3. Operacion con `dry_run=true` en preview y aprobacion manual antes de desactivar dry-run.
4. Auditoria `before` redaccionada.
5. Cambio de un solo campo de bajo riesgo.
6. Guardado manualmente aprobado.
7. Verificacion redaccionada del cambio.
8. Restauracion inmediata del valor original.
9. Verificacion redaccionada de restauracion.
10. Auditoria final con resultado y evidencia minima.

Estado actual: falta completar la primera prueba real de escritura externa por
plataforma/cuenta. La capacidad del Hub para editar datos internos esta verificada
con auditoria; el siguiente hito es ejecutar una escritura externa reversible en
una entidad autorizada.

Validacion local disponible: la pantalla `Transferencias` permite ejecutar
`upsert_worker` contra `connector_demo` en `mock_cae`. Esta prueba valida el job,
la auditoria y el resultado local. No sustituye el objetivo de escritura externa;
es el paso previo para llevar la misma operacion a un adaptador real de plataforma.

Reporte administrativo de datos obtenidos disponible:

```powershell
python scripts\build_arm_platform_obtained_data_report.py
```

Salida:

- `artifacts/admin-validation/arm_platform_obtained_data_latest.pdf`
- `artifacts/admin-validation/arm_platform_obtained_data_latest.html`

Este PDF solo incluye informacion observada o registrada desde plataformas:
contextos externos, capturas redaccionadas, etiquetas visibles, cabeceras,
formularios, estados agregados y observaciones de trabajador/documento. No se
usa para reportar capacidades, permisos, readiness, dry-run ni planes.

## Operaciones catalogadas

Operaciones de negocio cubiertas por manifiestos:

- `sync_company_profile`.
- `upsert_worker`.
- `deactivate_worker`.
- `upload_worker_document`.
- `upload_company_document`.
- `upload_machine_vehicle_document`.
- `read_external_status`.
- `read_rejections`.
- `download_receipt`.

Metodos de campo cubiertos por el catalogo de edicion:

- `fill_by_observed_label_or_name`: escritura de texto/email por etiqueta o nombre estable observado.
- `fill_date_by_observed_label_or_name`: escritura de fechas por etiqueta observada.
- `toggle_or_select_boolean_by_observed_label`: booleanos por etiqueta observada.
- `open_or_select_record_by_observed_label`: seleccion de registros relacionados.
- `upload_file_by_observed_file_input`: subida documental por input de fichero observado.
- `inject_from_configured_secret_store_at_login`: uso de credenciales cifradas configuradas, sin pedirlas al operador.
- `capture_edit_screen_before_method_binding`: falta captura editable antes de enlazar metodo.
- `readback_only_no_edit_method`: campo de lectura externa que no se edita desde el Hub.

Niveles de readiness:

- `verified_readonly_status_counts_available`: lectura real confirmada con valores/contadores externos agregados.
- `readonly_mapping_ready`: hay mapeo de lectura, pero falta validar que la ruta devuelve estados reales.
- `contract_proposed_needs_readonly_path_validation`: el contrato propone la operacion, falta ruta read-only validada.
- `contract_proposed_needs_write_screen_mapping`: hay contrato y login/captura parcial, falta mapear pantalla editable.
- `contract_proposed_needs_login_validation`: falta login validado.
- `proposal_missing_required_contract_fields`: faltan campos obligatorios en contrato/captura.
- `dry_run_mapping_ready_needs_reversible_write_probe`: queda lista para prueba reversible, pero no ejecutada.

## Uso futuro

1. Revisar `platform_operation_readiness.redacted.csv`.
2. Priorizar plataformas con login validado y gaps pequenos.
3. Completar capturas de pantallas de edicion sin guardar.
4. Aprobar mapeos en `/api/v1/platform-maps/labels`.
5. Crear manifiesto por operacion con selectores reales revisados.
6. Ejecutar primero `preview`.
7. Hacer prueba reversible solo en entidad dummy/sandbox.
8. Activar escrituras reales por plataforma/cuenta tras auditoria y aprobacion explicita.
