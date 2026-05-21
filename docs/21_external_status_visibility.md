# 21 - Visibilidad de estados documentales externos

Fecha: 2026-05-18.

## Objetivo

Cerrar la primera capa operativa para ver en el Hub los estados documentales comunicados por plataformas externas, sin activar escrituras ni inventar endpoints de proveedores.

La base legal revisada en `requisitos/iker_arm_base_legal_operativa_2026-05-18.zip` permite lectura de estados ARM en cuentas autorizadas, con `dry_run`, limites conservadores, captcha/MFA como `human_action_required` y sin bypass.

## Implementado

Backend:

- Servicio nuevo: `backend/app/services/platform_external_statuses.py`.
- API nueva: `GET /api/v1/platform-authorizations/external-statuses`.
- Reutiliza la tabla existente `external_document_statuses`; no hizo falta migracion.
- Devuelve plataforma, documento/version, tipo documental, entidad local, estado normalizado, color de semaforo y fecha de lectura.
- El servicio de runs queda preparado para persistir observaciones vinculadas a `document_version_id` cuando un conector autorizado las devuelva.

Frontend:

- `/authorizations` carga y muestra una tabla nueva: `Estados documentales por plataforma`.
- El historial de revisiones muestra resumen tecnico de terminos de estado detectados por el conector, si existen.

Conector e-coordina:

- Sigue siendo solo lectura.
- Mantiene login/contexto como antes.
- Abre `Documentacion -> Solicitudes de documentacion` con controles de navegacion reales detectados en captura autorizada.
- Enriquece evidencia con `external_status_summary` a partir de la columna real `documentacion_estado`, sin guardar filas personales ni cuerpos HTTP.
- No persiste estados si no puede enlazarlos de forma estable a una version documental local.

## Estados normalizados

El servicio normaliza textos externos a estados internos:

- `accepted`.
- `pending_external_validation`.
- `manual_required`.
- `rejected`.
- `expired_external`.
- `blocked_by_platform`.
- `not_applicable`.
- `unknown` o texto saneado si no hay equivalencia.

Color:

- Verde: aceptado o no aplica.
- Naranja: pendiente, requerido, en revision o desconocido.
- Rojo: rechazado, caducado externo o bloqueado por plataforma.

## Seguridad

- No se almacenan credenciales, cookies, tokens, HAR, cuerpos HTTP ni capturas con datos personales.
- Las observaciones persistidas deben estar vinculadas a documentos locales del tenant.
- No se guardan nombres o filas externas de trabajadores; la UI muestra entidad local ya existente.
- Si aparece captcha, MFA o aviso no determinista, el run debe quedar en `human_action_required`.
- Las escrituras externas siguen deshabilitadas y fuera de alcance.

## Validacion

Prueba backend ampliada:

- `test_transfer_demo_and_manual_export_zip` verifica que una transferencia demo genera estado externo persistido y visible por `GET /platform-authorizations/external-statuses`.

Validaciones ejecutadas:

```powershell
python -m ruff check backend\app backend\tests scripts\import_arm_platform_maps.py scripts\import_arm_first_priority_contracts.py
$env:PATH = "D:\PLATAFORMAS\.tools\node-v24.15.0-win-x64;$env:PATH"; npm.cmd run typecheck
python -m pytest backend\tests\test_mvp_api.py::test_transfer_demo_and_manual_export_zip -q
python -m pytest backend\tests
$env:PATH = "D:\PLATAFORMAS\.tools\node-v24.15.0-win-x64;$env:PATH"; npm.cmd test
```

## Pendiente

1. Definir reglas de enlace entre fila externa y `document_version_id` sin almacenar datos personales externos.
2. Ejecutar lectura e-coordina con credenciales por entorno y confirmar que el conector emite observaciones enlazadas.
3. Cuando existan observaciones enlazadas, persistirlas automaticamente desde `run-now` y reflejarlas en `/authorizations`.

## Mapeo e-coordina 2026-05-18

Ver `docs/22_e_coordina_status_mapping.md`.

La captura live de ARITEX confirma que `documentacion_estado` contiene estados reales agregables. En la lectura probada se detectaron `Validado=5` y `Caducado=4`, normalizados a `accepted` y `expired_external`.
