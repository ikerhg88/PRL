# 18 - Desarrollo inicial de contratos RPA ARM prioritarios

Fecha: 2026-05-18.

## Objetivo

Convertir las primeras plataformas ARM priorizadas en configuracion interna revisable, sin crear todavia conectores RPA ejecutables contra terceros.

Plataformas incluidas:

- e-coordina.
- 6conecta.
- Validate.
- Timenet.
- Nomio.
- Vitaly CAE.

## Estado implementado

Se anadio una capa de contratos/manifiestos RPA:

- `platform_rpa_manifests`: manifiesto por plataforma, tenant y prioridad.
- `platform_rpa_account_proposals`: cuentas saneadas del contrato, vinculadas a `PlatformAccount`.
- `platform_rpa_mapping_proposals`: propuestas de campos, tipos documentales y catalogos.

Migracion:

- `backend/alembic/versions/0012_platform_rpa_contracts.py`.

Servicio:

- `backend/app/services/platform_contracts.py`.

API:

```http
POST /api/v1/platform-contracts/import/arm-first-priority
GET /api/v1/platform-contracts/summary
GET /api/v1/platform-contracts/priority-slugs
GET /api/v1/platform-contracts/manifests
GET /api/v1/platform-contracts/accounts
GET /api/v1/platform-contracts/mappings
PATCH /api/v1/platform-contracts/mappings/{mapping_id}
```

Script local:

```powershell
python scripts\import_arm_first_priority_contracts.py
```

## Resultado demo local

Import ejecutado contra `storage/demo.db`:

- Manifiestos importados: 6.
- Cuentas ARM importadas: 11.
- `PlatformAccount` creadas/actualizadas: 11.
- Propuestas de mapeo importadas: 306.
- Omitidos: 0.

Smoke API:

- `GET /api/v1/platform-contracts/summary`: 6 manifiestos, 11 cuentas, 306 mapeos.
- `GET /api/v1/platform-contracts/manifests`: 6 filas.
- `GET /api/v1/platform-contracts/accounts`: 11 filas.
- `GET /api/v1/platform-contracts/mappings?mapping_kind=document_type`: 126 filas.

Todas las cuentas creadas quedan:

- `mode=disabled`.
- `dry_run=true`.
- `manual_approval_required=true`.
- `status=proposal_disabled`.

No se importan contrasenas. La API de cuentas no expone `credential_secret_ref`; solo quedan referencias internas para futura integracion con gestor de secretos.

## Que aporta

1. Permite revisar en UI/API que plataformas prioritarias ARM estan preparadas.
2. Mantiene separadas las cuentas propuestas de los conectores ejecutables.
3. Permite aprobar o marcar como pendiente cada campo o tipo documental.
4. Conecta con la fase previa de mapas estructurales: los mapeos aprobados podran cruzarse con `platform_discovered_labels`.
5. Deja listo el suelo para una futura API de preview de intercambio.

## Que no hace todavia

- No abre navegador.
- No ejecuta RPA.
- No sube documentos.
- No lee datos de terceros.
- No usa endpoints privados de proveedores.
- No activa escrituras externas.

## Proximo paso tecnico

Crear la API de preview de intercambio:

```http
POST /api/v1/exchange/{platform_account_id}/documents/preview
POST /api/v1/exchange/{platform_account_id}/workers/preview
POST /api/v1/exchange/{platform_account_id}/company/preview
```

El preview debe validar:

- Cuenta en `disabled` o `dry_run`, nunca ejecucion directa.
- Empresa local vinculada.
- Operacion incluida en manifiesto.
- Mapeos aprobados o pendientes marcados como bloqueo.
- Documento con SHA-256/version inmutable.
- Minimizacion de datos en Nomio y Timenet.
- Resultado siempre auditable y sin escritura externa.
