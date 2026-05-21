# 05 — Playbook de automatización de navegador autorizada

## 1. Propósito

Diseñar el módulo de automatización de navegador para IKER. Este módulo se usará solo cuando el titular de la cuenta tenga autorización para automatizar las operaciones y no exista una API disponible o adecuada.

## 2. Qué sí debe hacer

- Automatizar flujos repetitivos de formularios y subidas documentales permitidos.
- Usar credenciales válidas del titular de la cuenta o credenciales técnicas autorizadas.
- Operar con límites de velocidad conservadores.
- Pedir aprobación humana antes de acciones de escritura.
- Detenerse ante MFA, captcha, cambios inesperados, errores de sesión o condiciones no reconocidas.
- Registrar auditoría completa.
- Capturar evidencias mínimas y redaccionadas.
- Permitir modo `dry_run`.
- Permitir exportar un “plan de acciones” antes de ejecutar.

## 3. Qué no debe hacer

- No evadir licencias, paywalls, controles de acceso o términos aplicables.
- No saltar captcha, MFA ni controles anti-bot.
- No usar técnicas stealth ni ocultación.
- No rotar proxies para evitar límites.
- No explotar endpoints privados no documentados.
- No extraer datos fuera del alcance autorizado.
- No compartir credenciales entre clientes o tenants.

## 4. Flujo seguro de RPA

```text
1. Crear job en IKER.
2. Ejecutar preflight:
   - plataforma activa
   - permisos del usuario
   - credenciales existentes
   - modo permitido
   - requisitos completos
   - documento válido internamente
3. Generar plan de acciones:
   - login
   - navegar a entidad
   - localizar requisito
   - subir fichero
   - confirmar envío
   - capturar estado
4. Mostrar plan a usuario responsable.
5. Solicitar aprobación si hay escritura.
6. Ejecutar con Playwright.
7. Registrar cada paso.
8. Guardar resultado externo.
9. Programar polling de estado si procede.
```

## 4.1. Pasarela humana del Hub

Cuando aparece captcha, MFA, aviso legal o seleccion manual, el operador no trabaja
dentro de una copia de la web original. El Hub muestra una pasarela propia y claramente
separada:

- Operacion solicitada y plataforma/cuenta.
- Plan de pasos.
- Controles activos: `dry_run`, aprobacion manual y sin bypass.
- Boton para autorizar entrada en navegador visible.
- Registro de quien toma la decision humana.
- Lista de cambios externos planificados y cambios aplicados.

La pasarela no resuelve captcha ni MFA. Solo permite que una persona autorizada lo
haga en pantalla y despues registre el resultado. En la fase inicial solo queda
habilitada la accion fija `read_external_status`; subidas de documentos y otras
escrituras se muestran como opciones futuras deshabilitadas.

## 5. Arquitectura RPA

```text
rpa/
  browser_pool.py
  session_manager.py
  credentials_provider.py
  consent_policy.py
  platform_manifests/
    example_platform.yaml
  flows/
    login.py
    upload_document.py
    read_status.py
  evidence/
    screenshot_redactor.py
    html_snapshot_sanitizer.py
  tests/
```

## 6. Manifest de plataforma

Cada portal externo debe tener un manifiesto declarativo. Ejemplo:

```yaml
platform_key: example_cae
connector_type: rpa
base_url: "https://example.invalid"
status: disabled_by_default
requires_authorization_record: true
manual_approval_required: true
rate_limits:
  max_actions_per_minute: 6
  max_jobs_per_hour: 10
login:
  method: username_password
  mfa_behavior: stop_and_request_human
  captcha_behavior: stop_and_request_human
flows:
  upload_worker_document:
    enabled: false
    writes_external_system: true
    dry_run_supported: true
    selectors_version: 1
    selectors:
      login_email: "TODO_AUTHORIZED_SELECTOR"
      login_password: "TODO_AUTHORIZED_SELECTOR"
      submit_login: "TODO_AUTHORIZED_SELECTOR"
      search_worker: "TODO_AUTHORIZED_SELECTOR"
      upload_input: "TODO_AUTHORIZED_SELECTOR"
      submit_upload: "TODO_AUTHORIZED_SELECTOR"
```

## 7. Preflight obligatorio

Antes de ejecutar:

- Confirmar autorización configurada.
- Confirmar que el tenant tiene permiso interno para esa plataforma.
- Confirmar que el documento no contiene datos no requeridos.
- Confirmar que no existe API disponible configurada con mayor prioridad.
- Confirmar que no hay una exportación manual pendiente del mismo documento.
- Confirmar que el hash documental no fue enviado ya con la misma idempotency key.

## 8. Evidencias

Guardar solo lo necesario:

- ID de job.
- Fecha/hora.
- Plataforma.
- Entidad destino.
- Documento/tipo/hash.
- Resultado.
- Captura redaccionada si procede.
- HTML sanitizado si procede.

No guardar:

- Contraseñas.
- Cookies.
- Tokens.
- Páginas completas con datos personales innecesarios.
- Resultados médicos completos.

## 9. Gestión de errores

- `login_failed`: detener y solicitar revisión.
- `mfa_required`: detener y solicitar intervención humana.
- `captcha_detected`: detener; no resolver automáticamente.
- `selector_not_found`: detener y marcar conector para mantenimiento.
- `unexpected_layout`: detener y solicitar revisión.
- `upload_failed`: reintentar si es error temporal; si no, seguimiento manual.
- `rate_limited`: esperar o detener según política.

## 10. Priorización API > RPA > exportación

Orden recomendado:

1. API oficial o autorizada.
2. Exportación asistida si se necesita seguridad máxima.
3. RPA autorizada si el cliente necesita automatización y existe permiso suficiente.

## 11. Checklist de autorización por plataforma

Antes de activar RPA real:

- ¿Quién es titular de la cuenta?
- ¿La cuenta permite automatización?
- ¿Existe contrato, permiso o autorización escrita?
- ¿Qué datos se tratarán?
- ¿Quién es responsable/encargado del tratamiento?
- ¿Qué límites de uso aplican?
- ¿Qué operaciones serán solo lectura?
- ¿Qué operaciones escribirán en la plataforma?
- ¿Se requiere aprobación humana?
- ¿Hay mecanismos de exportación oficial?
