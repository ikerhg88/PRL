# 23 - Catalogo de traduccion de plataformas

Fecha: 2026-05-18.

## Objetivo

Construir una base reutilizable para traducir campos, accesos, formularios, cabeceras y estados entre plataformas externas y claves internas del Hub IKER PRL/CAE.

Este sistema no crea conectores comerciales reales, no usa endpoints privados como contrato API y no ejecuta escrituras externas.

## Fuentes procesadas

Se procesaron:

- Capturas tecnicas redaccionadas de `artifacts/platform-captures/`.
- Manifiestos y mapeos contractuales de `requisitos/iker_contratos_plataformas_max_scope_2026-05-18/`.
- Mapeo profundo redaccionado de e-coordina para `Documentacion -> Solicitudes de documentacion`.

No se incluyeron credenciales, cookies, tokens, HAR, cuerpos HTTP, capturas de pantalla ni valores de filas.

## Comando

```powershell
python scripts\build_platform_translation_catalog.py
python scripts\import_arm_platform_maps.py --replace
```

## Artefactos generados

Carpeta:

```text
artifacts/platform-translation/
```

Archivos:

- `platform_translation_catalog.redacted.json`: catalogo completo.
- `platform_translation_aliases.redacted.csv`: alias por clave canonica, plataforma y fuente.
- `platform_access_fields.redacted.csv`: accesos, campos, botones, cabeceras y columnas detectadas.
- `platform_summary.redacted.csv`: resumen por captura/plataforma.
- `platform_translation_summary.redacted.md`: resumen humano.

## Resultado de ejecucion

Resultado:

- Capturas procesadas: 35.
- Plataformas en catalogo de traduccion: 49.
- Plataformas con capturas redaccionadas: 22.
- Alias de traduccion: 1.428.
- Accesos/campos/cabeceras detectados: 1.714.
- Claves canonicas con alias: 48.
- Etiquetas pendientes sin clave canonica: 1.039.

Estados de login en capturas:

- `login_likely_success`: 12.
- `login_form_not_found`: 9.
- `login_not_confirmed_password_form_still_present`: 8.
- `stopped_control_detected_before_login`: 4.
- `initial_navigation_failed`: 2.

## Claves canonicas

La taxonomia vive en `backend/app/services/platform_mapping.py`.

Se amplio con campos de:

- Empresa: razon social, CIF/NIF, domicilio, email, telefono, CNAE/actividad.
- Trabajador: nombre, apellidos, DNI/NIE, NAF/SS, email, telefono, nacimiento, puesto, alta, baja, contrato y aptitud laboral minima.
- Documentos: tipo, fichero, emision, caducidad, solicitud, limite, recibido, validado, estado, incidencia e identificadores externos.
- Activos: maquinaria, vehiculos, matricula, serie, tipo de activo y productos quimicos.
- Accesos: usuario/password de login solo como forma de campo, nunca como valor.

## e-coordina

La cuenta ARM / ARITEX permite llegar a:

```text
Documentacion -> Solicitudes de documentacion
```

Campos/columnas reales confirmados:

- `documento`
- `documentacion_estado`
- `empresa`
- `trabajador`
- `centro`
- `puesto`
- `proyecto`
- `trabajo`
- `contratacion`
- `maquinaria`
- `vehiculo`
- `pq`
- `incidentado`
- `documento_tipo`
- `fecha_solicitado`
- `fecha_limite`
- `fecha_recibido`
- `fecha_validado`
- `fecha_emision`
- `fecha_caducidad`

Estados reales agregados confirmados:

- `Validado=5` -> `accepted`.
- `Caducado=4` -> `expired_external`.

## Capacidad para estados reales

El Hub ya puede recoger estados reales cuando se cumplen estas condiciones:

1. Login autorizado y confirmado sin captcha/MFA/control adicional.
2. Ruta read-only validada hasta una tabla o grid de solicitudes/documentos.
3. Columna de estado identificada sin guardar valores de filas.
4. Agregacion por estado o enlace minimizado a `document_version_id` con aprobacion humana.

Estado actual:

- Confirmado en e-coordina ARM/ARITEX para `documentacion_estado`.
- No confirmado aun para el resto de plataformas: el catalogo actual mapea accesos/campos/cabeceras y propuestas contractuales, pero no declara estados reales donde no exista una ruta read-only validada.

## Limites

- Las plataformas con captcha se detuvieron antes de login y no se reintentaron.
- Las plataformas con `login_form_not_found` o `login_not_confirmed_password_form_still_present` quedan mapeadas solo hasta la estructura visible segura.
- Los mapeos contractuales son propuestas pendientes de validacion de plataforma/proveedor.
- No se persisten estados por fila externa mientras no exista una regla minimizada para enlazar con `document_version_id`.

## Uso futuro

1. Revisar `platform_translation_aliases.redacted.csv`.
2. Aprobar o corregir equivalencias en `/api/v1/platform-maps/labels`.
3. Usar solo mapeos aprobados para generar previews de intercambio.
4. Mantener conectores RPA/API en `dry_run` y `manual_approval_required`.
5. Ejecutar escrituras externas solo con auditoria antes/despues y autorizacion explicita.
6. Usar `docs/24_platform_operation_catalog.md` para priorizar operaciones y gaps antes de construir selectores de escritura.
