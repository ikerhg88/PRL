# 16 - Sistema de mapeo estructural de plataformas

Fecha: 2026-05-18.

## Objetivo

Crear la capa previa a cualquier integracion RPA o API de intercambio: entrar en el conocimiento de cada plataforma desde capturas tecnicas redaccionadas, guardar su estructura visible, normalizar etiquetas y comparar que informacion o documentos son equivalentes entre plataformas.

Este modulo no crea conectores comerciales reales ni ejecuta escrituras externas. Su salida sirve para construir manifiestos, mapeos y jobs posteriores con `dry_run`, aprobacion humana y auditoria.

## Flujo funcional

1. Captura o entrada de estructura:
   - Fuente esperada: JSON redaccionado de captura tecnica autorizada.
   - No se guardan credenciales, cookies, tokens, HAR, cuerpos HTTP ni valores de trabajadores.
   - La captura contiene estructura: paginas, titulos, menus, formularios, inputs, botones y cabeceras de tabla.

2. Snapshot estructural:
   - Cada import genera una fila en `platform_structure_snapshots`.
   - Guarda tenant, plataforma/cuenta si se conoce, empresa, host, estado de login, fuente y JSON redaccionado.
   - Permite repetir la captura y conservar versiones historicas.

3. Etiquetado estandar:
   - El extractor lee headings, navegacion, cabeceras, campos de formulario y botones.
   - Genera filas en `platform_discovered_labels`.
   - Cada etiqueta conserva texto original, texto normalizado, pagina, tipo de etiqueta, entidad probable, clave estandar, confianza y estado de revision.

4. Comparacion entre plataformas:
   - La API agrupa etiquetas por `standard_key`.
   - Permite ver que plataformas piden lo mismo con nombres distintos, por ejemplo `DNI`, `NIF`, `Trabajador`, `Empleado`, `Fichero` o `Estado documental`.

5. Revision humana:
   - Las propuestas se crean como `proposed` si hay clave estandar y `needs_review` si no.
   - Un operador puede aprobar, corregir, desasociar o anotar cada etiqueta.
   - Toda correccion queda auditada.

6. Uso posterior para actualizar/modificar:
   - Los mapeos aprobados alimentaran manifiestos por proveedor.
   - Los jobs de intercambio validaran datos locales contra este mapa antes de previsualizar o enviar.
   - Las escrituras externas siguen separadas en jobs con `dry_run`, `manual_approval_required` y auditoria antes/despues.

## Variantes por plataforma

El mapa estructural no debe producir un unico camino generico. Debe permitir que
cada plataforma tenga varias variantes aprobables:

- Variante de login: una pantalla, dos pasos, SSO autorizado, aviso legal,
  seleccion posterior de empresa o sesion duplicada.
- Variante de contexto: como se confirma empresa, cliente final, centro,
  contrata o cuenta antes de leer datos.
- Variante de navegacion: como llegar a trabajadores, empresa, documentacion,
  incidencias, rechazos o historico.
- Variante de lectura: que cabeceras/etiquetas representan estado, caducidad,
  pendiente, rechazo, trabajador, empresa y tipo documental.
- Variante de mapeo: equivalencias entre etiquetas externas y claves internas
  del Hub, con estado `proposed`, `needs_review` o `approved`.

Cada variante debe conservar:

- Plataforma, tenant, cuenta externa y empresa local.
- Fuente de evidencia redaccionada o contrato/documentacion que la justifica.
- Senales usadas para reconocerla.
- Confianza y estado de revision.
- Fecha de ultima validacion.
- Fallback recomendado si no encaja.

Esto permite que la UI ofrezca acciones sencillas mientras el sistema elige la
variante correcta por detras. Si ninguna variante aprobada encaja, el resultado
debe ser `manual_followup_required` o `manual_export`, no una lectura inventada.

## Modelo de datos

Tablas nuevas:

- `platform_structure_snapshots`
  - `tenant_id`
  - `external_platform_id`
  - `platform_account_id`
  - `company_id`
  - `platform_label`
  - `host`
  - `login_status`
  - `source_type`
  - `source_ref`
  - `status`
  - `structure_json`
  - `summary_json`
  - `created_by`

- `platform_discovered_labels`
  - `tenant_id`
  - `snapshot_id`
  - `external_platform_id`
  - `platform_account_id`
  - `company_id`
  - `label_kind`
  - `raw_label`
  - `normalized_label`
  - `page_label`
  - `entity_scope`
  - `standard_key`
  - `confidence`
  - `review_status`
  - `metadata_json`
  - `notes`

Migracion:

- `backend/alembic/versions/0011_platform_structure_mapping.py`

## Taxonomia inicial

Claves estandar actuales:

- Empresa: `company.name`, `company.tax_id`.
- Centro/proyecto: `work_center.name`, `project.name`.
- Trabajador: `worker.full_name`, `worker.first_name`, `worker.last_name`, `worker.identifier_value`, `worker.identifier_expires_at`, `worker.nationality`, `worker.work_position`, `worker.medical_fitness_status`.
- Documento: `document.type`, `document.file`, `document.issued_at`, `document.expires_at`, `document.status`, `document.rejection_reason`.
- Maquinaria: `machine.record`, `machine.code`, `machine.manufacturer`, `machine.model`, `machine.serial`.
- Vehiculos: `vehicle.record`, `vehicle.plate`.
- Periodos y presencia: `period.start_date`, `period.end_date`, `attendance.checks`.

La taxonomia vive en `backend/app/services/platform_mapping.py` y debe evolucionar solo con pruebas y revision humana de ejemplos reales.

## API interna

Todas las rutas usan autenticacion, tenant y acceso amplio al tenant.

```http
GET /api/v1/platform-maps/standard-labels
GET /api/v1/platform-maps/snapshots
POST /api/v1/platform-maps/snapshots
GET /api/v1/platform-maps/labels
PATCH /api/v1/platform-maps/labels/{label_id}
GET /api/v1/platform-maps/compare
GET /api/v1/platform-maps/compare?standard_key=worker.identifier_value
```

Operaciones principales:

- Crear snapshot desde una estructura redaccionada.
- Listar snapshots por plataforma o cuenta.
- Listar etiquetas descubiertas por snapshot, plataforma, clave o estado de revision.
- Corregir una etiqueta y registrar auditoria.
- Comparar equivalencias entre plataformas.

## Import ARM actual

Comando:

```powershell
python scripts\import_arm_platform_maps.py --replace
python scripts\build_platform_translation_catalog.py
```

Resultado demo local del 2026-05-18:

- Snapshots importados: 35.
- Etiquetas estructurales creadas: 1.292.
- Catalogo de traduccion generado con 1.428 alias y 1.714 accesos/campos/cabeceras.
- Claves estandar detectadas en catalogo: 48.

Coincidencias destacadas:

- `worker.first_name`: visible en 6 plataformas/capturas.
- `company.name`: visible en 5 plataformas/capturas.
- `worker.full_name`: visible en 3 plataformas/capturas.
- `document.file`, `document.type`, `document.status` y `document.rejection_reason`: detectadas donde la estructura exponia formularios o secciones documentales.
- `worker.identifier_value`: visible como `jform[nif]` en 1 captura.

No se han ejecutado escrituras externas ni se ha reutilizado ningun endpoint privado de proveedor.

Detalle del catalogo de traduccion: `docs/23_platform_translation_catalog.md`.

## Relacion con las tres fases de trabajo

1. Mapear por web:
   - La fuente son capturas tecnicas redaccionadas o futuras capturas autorizadas.
   - El sistema guarda snapshots y etiquetas estandar.

2. Comparar plataformas:
   - `/platform-maps/compare` muestra que etiquetas equivalentes aparecen en cada plataforma.
   - Las diferencias quedan revisables antes de construir manifiestos.

3. Actualizar y modificar:
   - Este modulo no envia datos.
   - La futura API de intercambio usara solo mapeos aprobados para crear previews, validar alcance por empresa y preparar jobs RPA asistidos.

## Pendientes

1. Crear una UI de revision de etiquetas y comparacion por plataforma.
2. Asociar etiquetas aprobadas a manifiestos versionados por proveedor.
3. Ampliar taxonomia con tipos documentales CAE concretos cuando los contratos tecnicos lleguen.
4. Anadir import historico por lote con reporte CSV/XLSX de diferencias entre capturas.
5. Conectar el preview de intercambio para que use solo etiquetas `approved`.
