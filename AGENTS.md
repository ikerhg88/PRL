# AGENTS.md — Reglas del repositorio IKER PRL/CAE Hub

Estas instrucciones son obligatorias para Codex antes de crear, modificar o ejecutar código.

## Objetivo del producto

Construir un software propio de gestión PRL/CAE para centralizar empresas, trabajadores, maquinaria, vehículos, documentos, caducidades, requisitos y evidencias, con conectores independientes por plataforma externa.

## Objetivo operativo actual

El objetivo prioritario del proyecto es mapear plataformas CAE reales y ejecutar escrituras reales autorizadas cuando el flujo este validado de extremo a extremo. Cada iteracion debe acercar el producto a:

- descubrir y guardar rutas navegables reales de cada web/plataforma;
- capturar formularios, tablas, campos editables, botones y lecturas posteriores;
- convertir esas capturas en mapeos aprobables por plataforma, cuenta y contexto empresa-cliente;
- generar previews de escritura con datos locales reales;
- ejecutar altas, actualizaciones y subidas documentales solo cuando existan mapeo aprobado, autorizacion live, auditoria antes/despues y lectura posterior.

Los mocks, simuladores, conectores demo o datos de prueba solo sirven para tests, desarrollo local o validacion tecnica interna. No deben presentarse como progreso operativo CAE, no sustituyen una escritura real en plataforma comercial y no deben usarse para responder a una peticion cuyo objetivo sea escribir en una CAE autentica.

## Stack preferido

- Backend: Python FastAPI.
- Base de datos: PostgreSQL.
- ORM: SQLAlchemy 2.x o SQLModel.
- Migraciones: Alembic.
- Jobs: Redis + Celery o RQ.
- Frontend: Next.js + TypeScript.
- Almacenamiento documental: interfaz S3-compatible y modo local para desarrollo.
- Tests: pytest en backend; Vitest/Playwright en frontend.
- Desarrollo local y despliegue: servicios independientes del servidor, sin Docker ni contenedores salvo instruccion futura explicita.

## Principios Básicos

1. No inventar endpoints, rutas, selectores, credenciales ni estados.
2. Todo conector externo debe soportar `dry_run`, autorización real y auditoría.
3. Toda escritura externa requiere auditoría antes/después y lectura posterior si es posible.
4. Credenciales cifradas y nunca en logs.
5. Separación por tenant/empresa desde el inicio.
6. Tests antes de cerrar tareas.
7. README y migraciones al día.
8. No usar mocks/simuladores/demo como sustituto de integración CAE real.
9. Priorizar mapas y escrituras reales; si algo no puede escribirse, documentar exactamente qué falta.

## Diseño de conectores

Cada plataforma externa se implementará como un paquete independiente que cumple la interfaz común:

- `connector_api_*`: usa API oficial/documentada.
- `connector_rpa_*`: automatización de navegador autorizada y con revisión humana.
- `connector_export_*`: genera paquetes ZIP/Excel/PDF para subida manual.
- `connector_demo`: simula una plataforma externa en local solo para tests/desarrollo; no cuenta como escritura CAE real ni como avance operativo de integracion.

Los conectores RPA deben estar deshabilitados por defecto y activarse únicamente con configuración explícita por tenant, plataforma y cuenta.

## Metodo de conectores RPA de escritura protegida

Cada plataforma con escritura RPA debe tener un paquete propio bajo `backend/app/connectors/rpa/<plataforma>/` y registrarse en `backend/app/connectors/rpa/write_registry.py`. El conector debe heredar la interfaz comun y, si no existe un contrato especifico aprobado, usar el patron `ConfiguredWriteConnector` de `backend/app/connectors/rpa/common_write.py`.

El metodo actual para plataformas ARM es:

- Un conector independiente por plataforma y cuenta/empresa: `connector_rpa_e_coordina_write`, `connector_rpa_seisconecta_write`, `connector_rpa_ctaima_write`, `connector_rpa_nomio_write`, `connector_rpa_timenet_write`, `connector_rpa_validate_write` y `connector_rpa_vitaly_cae_write`.
- El catalogo de plataformas (`backend/app/platforms/catalog.py`) debe publicar esos conectores como `authorized_rpa_write` solo cuando existan en el registro.
- Toda ejecucion real requiere configuración explícita por tenant, plataforma y cuenta. La autorización puede ser por política, por lote o por acción, según la configuración vigente.
- Mientras no haya mapeo aprobado de campos, captura editable validada, preview de cambios, autorización configurada y auditoría antes/después, el resultado obligatorio es `blocked_mapping_review_required`.
- En ese estado bloqueado debe constar `external_write_executed=False` y `persist_external_status=False`; no se puede crear un estado externo como si se hubiera leido o escrito en la plataforma.
- El preview de escritura se genera mediante `POST /api/v1/exchange/{account_proposal_id}/preview`. Debe devolver campo por campo, valores locales redaccionados, bloqueos y `planned_external_changes`, manteniendo `external_write_enabled=false` hasta autorizacion live explicita.
- La accion de pasarela `capture_write_screen` sirve solo para capturar pantallas editables redaccionadas; no debe guardar cambios ni subir ficheros.
- No se deben inventar endpoints, rutas internas, selectores, credenciales ni estados. Si faltan evidencias de una pantalla o campo, se bloquea y se documenta la falta.
- No se resuelven captcha/MFA automaticamente. La pasarela solo guia al operador autorizado y conserva la separacion visual entre Hub y plataforma externa.

La documentacion operativa y de mapeo debe mantenerse con:

- `scripts/build_platform_field_edit_methods.py`: matriz de campos editables por plataforma, contexto empresa-cliente y requisito previo.
- `scripts/build_platform_obtained_data_mapping_report.py`: informe de datos obtenidos y correspondencias, sin datos inventados ni capacidades teoricas.
- `artifacts/platform-edit-methods/` y `artifacts/platform-obtained-mapping/`: salidas revisables para validacion administrativa.

Las pruebas minimas de este metodo son:

- El registro solo expone conectores permitidos.
- Cada conector de escritura responde `preview_available` en `test_connection`, `mapping_review_required` en `sync_catalog` y bloquea `upsert_worker`/`upload_document` sin escritura externa.
- El catalogo enlaza cada plataforma ARM con su conector real.
- `/api/v1/transfers` no persiste estados externos cuando el conector devuelve `persist_external_status=False`.
- `/api/v1/exchange/{account_proposal_id}/preview` informa bloqueos de mapeo/dato local sin escribir fuera y registra auditoria.
- Los informes no deben mezclar datos mock/test con datos ARM ni incluir descripciones de capacidad en informes que deban contener solo informacion obtenida.

## Qué significa “terminado”

Una tarea está terminada solo cuando:

- Hay código funcional.
- Hay tests relevantes.
- Hay migraciones si cambió el modelo de datos.
- Hay documentación actualizada.
- No hay secretos en el repositorio.
- Se ha ejecutado `make test` o comando equivalente.
- Los conectores externos reales no contienen endpoints ni selectores inventados.

## Comandos esperados

Codex debe crear estos comandos si no existen:

```bash
make dev
make test
make lint
make typecheck
make migrate
make seed
make e2e
```

## Convenciones de seguridad

- Logs estructurados con redacción de secretos.
- Hash SHA-256 de cada documento.
- Versionado documental inmutable.
- Auditoría append-only.
- RBAC por tenant, rol, centro, proyecto y permiso.
- Principio de mínimo privilegio.
- Política de retención configurable.

## Continuidad del proyecto

Antes de continuar el desarrollo en otra sesion:

1. Leer este `AGENTS.md`.
2. Leer todos los documentos de `docs/`, especialmente `docs/10_continuation_state.md`.
3. Hacer caso al prompt actual si contradice una decision anterior.
4. No introducir Docker ni contenedores salvo instruccion futura explicita.
5. No crear conectores comerciales reales, endpoints inventados, selectores RPA ni credenciales de terceros.
6. Mantener la separacion entre gestion del sistema, gestion del tenant/empresa y datos operativos CAE.
7. Ejecutar pruebas antes de cerrar cualquier iteracion.

Checkpoint vigente:

- Producto local: `scripts/start-product.ps1`.
- Frontend local: `http://127.0.0.1:3000`.
- Backend local: `http://127.0.0.1:8001`.
- Usuario demo principal: `admin@demo.invalid` / `DemoPassword123!`.
- Estado detallado, validaciones y siguientes pasos: `docs/10_continuation_state.md`.
