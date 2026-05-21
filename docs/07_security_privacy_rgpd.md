# 07 — Seguridad, privacidad y RGPD

## 1. Principio general

IKER tratará datos laborales, identificativos y documentación potencialmente sensible. Debe diseñarse con privacidad desde el inicio, minimización y trazabilidad.

## 2. Datos especialmente sensibles

### Aptitud médica

Guardar únicamente:

- Estado: apto, no apto, apto con restricciones, renuncia, pendiente.
- Fecha de emisión.
- Fecha de caducidad.
- Documento justificativo mínimo cuando sea imprescindible.
- Restricciones preventivas solo si son necesarias para adaptar el puesto y sin detalles clínicos.

No guardar:

- Diagnósticos.
- Pruebas médicas.
- Historial clínico.
- Datos de salud no necesarios para CAE.

## 3. Minimización

- Identificadores personales cifrados o tokenizados si es posible en despliegues productivos.
- El producto puede mostrar DNI/NAF completos cuando el cliente aporta base legal/autorizacion y necesita operar con esos datos.
- Hash/últimos 4 caracteres siguen siendo utiles para busquedas internas cuando baste, pero no sustituyen la ficha operativa autorizada.
- Documentos completos solo si son necesarios para cumplir un requisito.
- Retención por tipo documental.

## 4. Roles y permisos

Roles iniciales:

- `tenant_admin`.
- `prl_manager`.
- `cae_operator`.
- `document_reviewer`.
- `work_center_viewer`.
- `auditor`.

Permisos:

- `company.read/write`.
- `worker.read/write`.
- `document.read/write/validate/delete`.
- `requirement.read/write`.
- `connector.read/write/execute/approve`.
- `audit.read`.
- `settings.write`.

Los permisos efectivos deben calcularse cruzando:

- Rol del usuario en el tenant.
- Accesos multiempresa.
- Grants granulares por `scope_type/scope_id`.
- Denegaciones explicitas `deny`, que prevalecen sobre permisos `allow`.

## 5. Auditoría

Registrar:

- Login/logout.
- Subida/descarga documental.
- Validación/rechazo.
- Cambio de caducidad.
- Cambio de requisitos.
- Creación/ejecución de jobs.
- Activación/desactivación de conectores.
- Acceso a documentos sensibles.

## 6. Secretos

- Cifrado con KMS o vault.
- No guardar contraseñas en variables de entorno compartidas.
- Las passwords de usuarios locales se guardan como hash PBKDF2-SHA256 con sal; nunca en claro.
- Los tokens de verificacion de email se guardan solo como SHA-256 y con caducidad/consumo unico.
- Rotación.
- Separación por tenant.
- Redacción en logs.
- Nunca exportar secretos en paquetes manuales.

### SSO/OIDC

- El signup local exige verificacion de email antes de login.
- El signup SaaS con Google se inicia sin tenant y crea tenant/empresa solo tras validar `state`, `nonce`, PKCE, firma, audiencia, issuer y email verificado.
- Google Workspace se configura por tenant como proveedor OIDC.
- El `client_secret` se guarda solo en variables de entorno o vault, nunca en base de datos ni repositorio.
- La configuracion no secreta de SSO vive en `config/iprl-cae.config.toml`; secretos OAuth, SMTP y credenciales externas viven solo en entorno o vault.
- Las transacciones SSO deben usar `state`, `nonce` y PKCE.
- El backend debe validar firma, audiencia, issuer, expiracion, `nonce` y dominio permitido antes de crear sesion local.
- No se persisten `access_token`, `refresh_token` ni perfiles completos de Google; solo identidad enlazada minima.

## 7. Documentos

- Hash SHA-256.
- Versionado inmutable.
- Diferenciar caducidad declarada por la empresa de caducidad comunicada por plataforma externa.
- Marcar para revision las diferencias de caducidad antes de sobrescribir criterios internos.
- Antivirus/escaneo.
- Control de MIME y tamaño.
- Enlaces temporales para descarga.
- Watermark opcional en descargas.

### OCR documental

- El OCR crea propuestas pendientes de revision, no versiones documentales definitivas.
- No guardar el texto OCR completo salvo necesidad justificada; preferir extracto redaccionado y señales estructuradas.
- La asignacion a trabajador/empresa/tipo documental debe mostrar confianza y razones.
- La aprobacion humana es obligatoria antes de crear una version documental.
- En aptitud laboral, no extraer ni estructurar diagnosticos, pruebas ni historial clinico.

## 8. Conectores externos

- Data Processing Agreement cuando aplique.
- El acceso de usuarios a plataformas se asigna por `PlatformAccount`, no por credenciales compartidas.
- Revocar un usuario de una plataforma debe mantener auditoria y no borrar evidencias historicas.
- Registro de autorización de automatización por plataforma.
- Evidencias mínimas.
- Prohibición de compartir credenciales entre tenants.
- Bloqueo ante anomalías.

## 9. Retención

Definir por tipo documental:

- Documentos caducados: conservar por periodo legal/configurable.
- Documentos rechazados: conservar si justifican auditoría; purgar si no son necesarios.
- Evidencias RPA: conservar solo el mínimo imprescindible.
- Logs: retención separada y sin datos sensibles innecesarios.

## 10. Evaluación de impacto

Recomendada si se incorporan:

- Biometría.
- Control de accesos físico.
- Perfilado automatizado de riesgo.
- IA para validación automática sin revisión humana.
- Tratamiento masivo de datos de trabajadores.
