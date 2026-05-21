# 20 - Piloto directo e-coordina solo lectura

Fecha: 2026-05-18.

## Plataforma piloto

- Plataforma: e-coordina.
- Slug: `e_coordina`.
- Cuenta probada: ARM / ARITEX, fila local ARM 4.
- URL probada: `https://v5.e-coordina.com/aritex`.
- Modo: RPA autorizada de solo lectura.

## Base legal/operativa revisada

Fuente: `requisitos/iker_arm_base_legal_operativa_2026-05-18.zip`.

El paquete declara:

- 20 plataformas ARM.
- 34 cuentas ARM saneadas.
- e-coordina con 6 cuentas ARM activas.
- Autorizacion de lectura sobre entidades ARM vinculadas.
- Frecuencia maxima de lectura: hasta cada hora por cuenta ARM y diario base.
- Captcha/MFA/aviso: `human_action_required`, navegador visible, sin bypass.
- Escrituras: solo bajo `preview`, aprobacion manual y auditoria.

## Captura directa ejecutada

Se ejecuto una captura tecnica directa con:

```powershell
python scripts\capture_arm_platform_readonly.py `
  --excel "D:\PLATAFORMAS\requisitos\USUARIOS Y CONTRASEÑAS PLATAFORMASulo.xlsx" `
  --sheet ARM `
  --row 4 `
  --out-dir D:\PLATAFORMAS\artifacts\platform-captures `
  --max-pages 2
```

Resultado:

- `login_status=login_likely_success`.
- Captcha detectado: `false`.
- MFA/OTP detectado: `false`.
- Contexto visible: `e-coordina - ARITEX`.
- Hosts principales observados: `v5.e-coordina.com`, `static.e-coordina.com`.
- Artefacto redaccionado:
  - `artifacts/platform-captures/arm-aritex-20260518-152257/technical_capture.redacted.md`.
  - `artifacts/platform-captures/arm-aritex-20260518-152257/technical_capture.redacted.json`.

La revision de artefactos no encontro contraseñas, cookies, tokens, autorizaciones bearer ni identificadores personales en claro. Las menciones a `password` corresponden a presencia/campo de formulario y no al valor secreto.

## Conector implementado

Backend:

- Conector: `backend/app/connectors/rpa/e_coordina/readonly.py`.
- Servicio de runs: `backend/app/services/platform_review_runs.py`.
- Resolucion de secretos: `backend/app/services/platform_credentials.py`.
- Migracion: `backend/alembic/versions/0014_platform_review_runs.py`.
- API:
  - `POST /api/v1/platform-review-schedules/{schedule_id}/run-now`.
  - `GET /api/v1/platform-review-schedules/{schedule_id}/runs`.

Frontend:

- `/authorizations`.
- Boton: `Probar lectura`.
- Historial visible de ejecuciones de revision por plataforma.

Runner local:

- Script: `scripts/run_due_platform_reviews.py`.
- Lista schedules vencidos sin ejecutar:

```powershell
python scripts\run_due_platform_reviews.py --tenant-id 1 --list-only
```

- Ejecuta schedules vencidos:

```powershell
python scripts\run_due_platform_reviews.py --tenant-id 1
```

El runner usa la misma proteccion del endpoint: si `features.platform_rpa_connectors` o `connectors.rpa_enabled` estan desactivados, la ejecucion queda registrada como `blocked_feature_disabled` y recalcula la siguiente revision sin acceder a terceros.

## Resultado del conector directo

Se ejecuto el nuevo conector con credenciales solo en memoria desde el Excel local. Resultado redaccionado:

- `status=completed`.
- `result_status=login_likely_success`.
- `result_summary=Login directo e-coordina confirmado en modo solo lectura`.
- `captcha_detected=false`.
- `mfa_detected=false`.
- `context_detected=true`.

No se guardaron credenciales, cookies, tokens, HAR, capturas ni cuerpos HTTP.

## Configuracion para ejecucion desde API

Por seguridad, el endpoint `run-now` solo ejecuta RPA real si estan activos:

- `features.platform_rpa_connectors=true`.
- `connectors.rpa_enabled=true`.

Y si se proporciona el secreto mediante variables de entorno. Para una cuenta concreta:

```powershell
$env:IPRL_CAE_PLATFORM_CREDENTIALS_E_COORDINA_ARM_R4_ARITEX='{"username":"...","password":"..."}'
```

Tambien se admiten variables separadas:

```powershell
$env:IPRL_CAE_PLATFORM_CREDENTIALS_E_COORDINA_ARM_R4_ARITEX_USERNAME='...'
$env:IPRL_CAE_PLATFORM_CREDENTIALS_E_COORDINA_ARM_R4_ARITEX_PASSWORD='...'
```

El valor nunca se devuelve por API ni se escribe en auditoria.

## Limites actuales del piloto

- El conector confirma login y contexto e-coordina/ARITEX.
- El conector navega en modo solo lectura a `Documentacion -> Solicitudes de documentacion`.
- La pantalla documental expone `documentacion_estado`; en ARITEX se confirmaron estados agregados reales `Validado=5` y `Caducado=4`.
- Todavia no extrae ni persiste estados por trabajador/documento porque falta aprobar un enlace minimo entre fila externa y `document_version_id` local sin guardar datos personales externos.
- No usa endpoints privados observados como API contractual.
- No realiza escrituras.
- Si aparece captcha/MFA/aviso no determinista, devuelve `human_action_required`.

## Siguiente paso tecnico

Convertir el conteo agregado real en lectura enlazada por documento local:

1. Definir una regla segura de correspondencia entre fila externa y documento local.
2. Capturar solo identificadores minimos permitidos o hashes, nunca listados personales completos.
3. Emitir observaciones enlazadas a `document_version_id`.
4. Persistir estados en `external_document_statuses`.
5. Reflejar incidencias en `/authorizations`.

Detalle: `docs/22_e_coordina_status_mapping.md`.
