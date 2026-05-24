# 12 - Carga documental ARM

Fecha: 2026-05-18.

## Alcance

Se incorporaron a la demo local documentos propios de ARM desde `requisitos/` mediante flujo de intake documental. La carga no aprueba documentos automaticamente ni crea versiones definitivas; todo queda pendiente de revision humana.

## Modulos usados

- `POST /api/v1/document-intake/bulk-upload`: importa ZIP documentales con alcance `company` o `multiple_workers`.
- `GET /api/v1/workers/intake-proposals?company_id={id}`: propone trabajadores a partir de nombres evidentes en documentos pendientes.
- `POST /api/v1/workers/import-from-intake`: crea fichas minimas con `dry_run=true` por defecto y auditoria.

## Resultado local

Empresa:

- `ARM Industrial Assemblies, S.L.`
- `company_id=5`
- `tax_id=B95868543`

Documentos cargados:

- `Documentación empresa ARM.zip`: 7 propuestas de empresa en `pending_review`.
- `replataformasycontraseas.zip`: 32 propuestas de trabajadores en `pending_review`.

Trabajadores creados desde propuestas:

- Eleder Bilbao.
- Jose Manuel Alvarez.
- Santiago Garcia Fernandez.
- Alejandro Pendiente revisar.
- Alfonso Pendiente revisar.
- David Pendiente revisar.
- Ivan Pendiente revisar.

## Criterios de seguridad

- No se han guardado DNI, NAF ni otros identificadores inferidos desde nombres de archivo.
- Los trabajadores con apellidos no evidentes quedan como `Pendiente revisar`.
- Las fichas tienen notas CAE indicando que proceden de intake y requieren revision antes de aprobar documentos.
- Los documentos siguen en `pending_review` hasta aprobacion manual con tipo documental, entidad y fechas confirmadas.
