# AGENTS.md — Reglas del repositorio IKER PRL/CAE Hub

Estas instrucciones son obligatorias para Codex antes de crear, modificar o ejecutar código.

## Objetivo del producto

Construir un software propio de gestión PRL/CAE para centralizar empresas, trabajadores, maquinaria, vehículos, documentos, caducidades, requisitos y evidencias, con conectores independientes por plataforma externa.

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

## Principios obligatorios

1. No inventar endpoints reales de plataformas comerciales.
2. No implementar bypass de captcha, MFA, controles anti-bot, rate limits, paywalls, licencias, restricciones contractuales o controles de acceso.
3. No usar proxy rotation, user-agent spoofing engañoso, técnicas stealth o mecanismos de ocultación.
4. Todo conector externo debe tener modo `dry_run` y `manual_approval_required`.
5. Toda acción de escritura externa debe generar auditoría antes y después de ejecutarse.
6. Las credenciales de plataformas externas deben guardarse cifradas y nunca en logs.
7. No almacenar historiales médicos ni resultados clínicos. En vigilancia de salud laboral, guardar únicamente aptitud laboral, restricciones preventivas si aplica, emisión/caducidad y evidencia documental mínima.
8. Separar datos por tenant/empresa desde el primer commit.
9. Ejecutar tests antes de declarar una tarea terminada.
10. Mantener README y migraciones al día.

## Diseño de conectores

Cada plataforma externa se implementará como un paquete independiente que cumple la interfaz común:

- `connector_api_*`: usa API oficial/documentada.
- `connector_rpa_*`: automatización de navegador autorizada y con revisión humana.
- `connector_export_*`: genera paquetes ZIP/Excel/PDF para subida manual.
- `connector_demo`: simula una plataforma externa en local.

Los conectores RPA deben estar deshabilitados por defecto y activarse únicamente con configuración explícita por tenant, plataforma y cuenta.

## Metodo de conectores RPA de escritura protegida

Cada plataforma con escritura RPA debe tener un paquete propio bajo `backend/app/connectors/rpa/<plataforma>/` y registrarse en `backend/app/connectors/rpa/write_registry.py`. El conector debe heredar la interfaz comun y, si no existe un contrato especifico aprobado, usar el patron `ConfiguredWriteConnector` de `backend/app/connectors/rpa/common_write.py`.

El metodo actual para plataformas ARM es:

- Un conector independiente por plataforma y cuenta/empresa: `connector_rpa_e_coordina_write`, `connector_rpa_seisconecta_write`, `connector_rpa_ctaima_write`, `connector_rpa_nomio_write`, `connector_rpa_timenet_write`, `connector_rpa_validate_write` y `connector_rpa_vitaly_cae_write`.
- El catalogo de plataformas (`backend/app/platforms/catalog.py`) debe publicar esos conectores como `authorized_rpa_write` solo cuando existan en el registro.
- Toda ejecucion real empieza en `dry_run` y `manual_approval_required`.
- Mientras no haya mapeo aprobado de campos, captura editable validada, preview de cambios, autorizacion humana y auditoria antes/despues, el resultado obligatorio es `blocked_mapping_review_required`.
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
