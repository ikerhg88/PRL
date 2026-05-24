# 04 — Framework de conectores

## 1. Objetivo

Permitir que IKER conecte con múltiples plataformas CAE sin acoplar el núcleo del producto a cada proveedor. Cada conector debe ser independiente, testeable y sustituible.

## 2. Tipos de conector

### 2.1. API

Para APIs oficiales, públicas, documentadas o autorizadas contractualmente.

Ventajas:

- Más estable.
- Menos riesgo operativo.
- Mejor observabilidad.
- Menos mantenimiento.

### 2.2. RPA autorizada

Automatización de navegador para acciones permitidas. Debe reproducir flujos de usuario con credenciales propias, sin evadir controles, con revisión humana y límites operativos.

Uso adecuado:

- Plataformas sin API pública.
- Operaciones repetitivas autorizadas.
- Portales del propio cliente o donde el cliente autorice expresamente la automatización.

### 2.3. Exportación asistida

Genera un paquete listo para carga manual:

- ZIP.
- Excel/CSV.
- README.
- Checklist.
- Evidencias.

Debe existir siempre como fallback.

## 3. Contrato funcional común

Operaciones mínimas:

- `authenticate`.
- `testConnection`.
- `syncCatalog`.
- `upsertCompany`.
- `upsertWorker`.
- `upsertMachine`.
- `upsertVehicle`.
- `uploadDocument`.
- `getDocumentStatus`.
- `getAccessStatus`.

### 3.1. ERPs externos

Los conectores ERP importan o actualizan maestros internos: trabajadores, empresas, puestos y asignaciones a obras. Deben cumplir las mismas reglas: API oficial/autorizada, `dry_run`, mapeo por tenant, auditoria y sin endpoints inventados.

## 4. Ciclo de vida de un job

1. `created`.
2. `preflight_pending`.
3. `preflight_ok` o `preflight_failed`.
4. `approval_pending` si procede.
5. `queued`.
6. `running`.
7. `submitted`.
8. `polling_status`.
9. `completed` o `failed`.
10. `manual_followup_required` si no se puede completar automáticamente.

## 5. Idempotencia

Toda operación externa debe tener clave de idempotencia:

```text
tenant_id:platform_id:operation:entity_type:entity_id:document_version_sha256
```

## 6. Mapeos

Cada plataforma puede tener:

- Campos propios.
- Nombres de documentos propios.
- Reglas de caducidad propias.
- Estados propios.
- Observaciones propias.

El conector nunca debe modificar el catálogo global sin aprobación. Los mapeos propuestos deben quedar en estado `pending_review`.

Cada cuenta de plataforma se administra por tenant. Los usuarios internos se asignan a `PlatformAccount` con nivel de acceso, permisos y operaciones permitidas; no se comparten credenciales entre usuarios ni tenants.

Separacion de responsabilidades:

- Tenant/empresa: `PlatformAccount`, `PlatformAccountUserAccess`, mapeos, permisos y operaciones habilitadas para el cliente.
- Sistema: registry de conectores, modulos instalados, health tecnico y catalogo global de metodos.

### 6.1. Paths de escritura por cuenta

Los paths de escritura observados se guardan en `platform_write_paths`, siempre
asociados a tenant, plataforma, cuenta externa y operacion. Sirven para recordar
como llegar a un formulario o lectura posterior en una combinacion concreta
plataforma+empresa+centro.

Reglas:

- Un path nace en `pending_review`; no puede activar escritura hasta aprobacion.
- Para aprobarlo debe tener evidencia o captura asociada, `field_paths` y
  `readback_paths`.
- El path puede guardar etiquetas, rutas y selectores redaccionados, pero nunca
  credenciales, cookies, tokens ni valores reales de formularios.
- Un preview puede usar paths `approved` para preparar cambios; el submit live
  sigue requiriendo dry-run previo, autorizacion humana, auditoria antes/despues
  y lectura posterior confirmada.

## 7. RPA manifest

Cada conector RPA debe declarar:

- URL base.
- Versión del portal si se conoce.
- Flujos soportados.
- Selectores versionados.
- Acciones de escritura.
- Evidencias capturadas.
- Límites por minuto/hora.
- Requisitos de aprobación.
- Método de login.
- Qué hacer si aparece MFA/captcha: detener y solicitar intervención humana.

El manifiesto no debe asumir que todas las plataformas se comportan igual. Cada
proveedor puede declarar varios metodos y variantes:

- `login_methods`: login en una pantalla, login en dos pasos, selector de cuenta
  posterior, SSO autorizado, aviso legal o sesion ya abierta.
- `account_context_methods`: confirmacion de empresa/cliente antes de operar.
- `navigation_recipes`: rutas semanticas hacia trabajadores, empresa,
  documentacion, incidencias y rechazos.
- `read_mapping_variants`: columnas, etiquetas y estados externos que se pueden
  leer y traducir al modelo interno.
- `write_mapping_variants`: campos y documentos que se pueden preparar en
  preview; solo se activan con mapeo aprobado, dry-run y aprobacion humana.
- `human_handoff_points`: captcha, MFA, sesion duplicada, selector ambiguo,
  pantalla inesperada o datos fuera de alcance.

La UI debe esconder esta complejidad. El usuario ve acciones simples y guiadas;
el conector selecciona internamente la variante segura, muestra el progreso y
solo pide intervencion cuando exista una decision o validacion humana real.

## 8. Seguridad

- Nunca logar contraseñas, tokens, cookies, PDFs completos o datos personales innecesarios.
- Redactar screenshots si contienen datos sensibles.
- Guardar evidencias solo cuando sean necesarias.
- Cifrar secretos.
- Rotar credenciales.
- Bloquear conector si hay errores repetidos.

## 9. Estados normalizados

Cada conector debe traducir estados externos a estados internos:

```text
external_accepted -> accepted
external_pending -> pending_external_validation
external_rejected -> rejected
external_missing -> not_synced
external_expired -> expired_external
external_unknown -> unknown
```

## 10. Tests obligatorios por conector

- Test de contrato.
- Test de autenticación simulada.
- Test de mapeo documental.
- Test de subida en modo dry-run.
- Test de idempotencia.
- Test de redacción de secretos.
- Test de fallo/reintento.
- Test de auditoría.
