# 01 — Especificación de producto: IKER PRL/CAE Hub

## 1. Visión

IKER PRL/CAE Hub será una plataforma propia para centralizar documentación, requisitos y estados de PRL/CAE, con conectores independientes por plataforma externa. El objetivo es que una empresa mantenga una base documental única y pueda distribuir, consultar o preparar documentación para distintas plataformas sin repetir trabajo manual.

## 2. Personas usuarias

- Administrador de tenant: configura empresa, usuarios, permisos y conectores.
- Técnico PRL: gestiona requisitos, revisa documentos, resuelve incidencias.
- Administrativo CAE: sube documentos, corrige rechazos, lanza sincronizaciones.
- Responsable de centro/obra: consulta semáforos de aptitud documental.
- Auditor interno: revisa trazabilidad, evidencias y cambios.
- Trabajador/contrata: aporta documentación si se habilita portal externo.

## 3. Problemas a resolver

- Repetición de cargas documentales en múltiples plataformas.
- Falta de trazabilidad centralizada.
- Caducidades dispersas.
- Requisitos diferentes por cliente, centro, actividad o plataforma.
- Falta de visión unificada de estados.
- Pérdida de tiempo en tareas administrativas.
- Rechazos documentales no normalizados.

## 4. Principios de producto

1. Base documental única.
2. Requisitos configurables.
3. Estado por plataforma, no solo estado interno.
4. Conectores independientes.
5. Sin dependencia obligatoria de una plataforma externa.
6. Exportación asistida como fallback universal.
7. Revisión humana para operaciones sensibles.
8. Auditoría completa.
9. Privacidad desde el diseño.

## 5. Módulos funcionales

### 5.0. Separacion de administracion

La aplicacion distingue dos planos:

- Gestion propia de empresa/tenant: empresas, trabajadores, documentos, requisitos, cuentas de plataformas, usuarios autorizados por plataforma y transferencias.
- Gestion del sistema: modulos instalados, conectores disponibles, health tecnico, catalogo global y capacidad operativa del runtime.

La gestion del sistema no debe contener credenciales ni datos documentales de clientes.

### 5.1. Gestión de empresas

- Empresa propia.
- Clientes.
- Contratas/subcontratas.
- Centros de trabajo.
- Obras/proyectos.
- Actividades.
- Contratos y fechas.

### 5.2. Gestión de trabajadores

- Datos identificativos mínimos.
- DNI/identificador completo y Seguridad Social completa cuando el usuario los aporte con autorizacion de tratamiento.
- Relación con empresa/centro/proyecto.
- Alta manual, borrado/baja auditada, carga masiva CSV e importacion desde ERPs autorizados.
- Puesto/actividad.
- Formación PRL.
- Cursos disponibles, proveedor, horas, fecha de emision, caducidad y documento asociado.
- Aptitud laboral.
- Revision medica con estado operativo, fecha de emision/caducidad, proveedor y restricciones no clinicas.
- Entrega de EPIs.
- Autorizaciones de equipos.
- Estado documental.
- Plataformas donde esta dado de alta y obras/centros/proyectos donde participa.

### 5.3. Maquinaria, vehículos y equipos

- Vehículos.
- Maquinaria.
- Equipos de trabajo.
- Seguros, ITV, revisiones, autorizaciones.
- Asociación a trabajador/empresa/proyecto.

### 5.4. Gestión documental

- Tipos documentales.
- Versiones.
- Emision/caducidad declarada por empresa.
- Caducidad comunicada por plataforma y estado de revision cuando no coincide con la declarada.
- Hash SHA-256.
- OCR/extracción asistida.
- Validación humana.
- Observaciones.
- Rechazos.
- Histórico.

La configuracion de empresa permite editar datos de la empresa autorizada y cargar sus documentos. Los documentos de trabajador se consultan y cargan desde la ficha del trabajador. En ambos casos se muestran caducidad declarada por empresa y caducidad comunicada por plataforma.

### 5.5. Reglas CAE

- Plantillas por obra, cliente, centro, actividad, puesto, riesgo y plataforma.
- Documentos exigidos por entidad: empresa, trabajador, máquina, vehículo.
- Reglas de caducidad.
- Bloqueo de acceso.
- Comprobacion de estado por empresa o trabajador.
- Alertas.

En la interfaz este modulo se llama Reglas CAE. El termino tecnico `requirements` queda reservado a rutas internas y API para mantener compatibilidad.

### 5.6. Conectores de plataformas

Tres tipos:

- API: integración oficial/documentada.
- RPA autorizada: automatización de navegador con credenciales propias y revisión humana.
- Exportación asistida: ZIP/Excel/PDF/instrucciones para subir manualmente.

En la version actual no hay conectores comerciales activos. Existe `mock_cae` como plataforma local para probar configuracion, permisos, mapeos y exportacion manual sin terceros. Ademas, el catalogo incluye plataformas comerciales investigadas en `docs/09_platform_api_research.md`; quedan en modo preparatorio con `manual_export` y metodos API/RPA deshabilitados hasta disponer de contrato y documentacion oficial.

El administrador debe poder ver las plataformas activas, crear cuentas/configuraciones por plataforma y asignar usuarios internos con permisos de operacion por plataforma.
La ficha del trabajador debe mostrar su presencia en plataformas y el estado externo normalizado por plataforma/cuenta.

El modelo de permisos debe permitir cruzar usuarios, multiples empresas y permisos concretos, con grants `allow/deny` por ambito para aplicar minimo privilegio.

### 5.6.bis. Conectores ERP

Los trabajadores pueden entrar al sistema por:

- Alta manual.
- Carga masiva CSV.
- Conector ERP oficial/autorizado.

Los conectores ERP reales no deben inventar endpoints ni credenciales. Deben declararse por tenant, operar en `dry_run` hasta validacion y registrar auditoria de altas/actualizaciones.

### 5.7. Panel de transferencias

Inspirado en Konvergia:

- Fecha/hora.
- Empresa/trabajador.
- Origen.
- Destino.
- Tipo documental.
- Fichero.
- Código documental.
- Estado de job.
- Resultado externo.
- Evidencia.

### 5.8. Dashboard

- Documentos válidos/caducados/próximos a caducar.
- Trabajadores aptos/no aptos documentalmente.
- Estado por plataforma.
- Rechazos pendientes.
- Jobs fallidos.
- Riesgo por cliente/centro.

## 6. Estados documentales internos

- `missing`: falta documento.
- `draft`: documento cargado pero sin enviar/validar.
- `pending_internal_review`: pendiente de revisión interna.
- `valid_internal`: válido según reglas internas.
- `expiring_soon`: próximo a caducar.
- `expired`: caducado.
- `rejected_internal`: rechazado internamente.
- `not_applicable`: no aplica.

## 7. Estados externos por plataforma

- `not_synced`.
- `queued`.
- `submitted`.
- `pending_external_validation`.
- `accepted`.
- `accepted_with_warnings`.
- `rejected`.
- `expired_external`.
- `unknown`.
- `manual_required`.
- `blocked_by_platform`.

## 8. MVP 1

Objetivo: sistema útil sin integraciones externas reales.

Incluye:

- Multi-tenant básico.
- CRUD de empresas, centros, trabajadores, cursos PRL, documentos y tipos documentales.
- Alta manual, edicion, baja/restauracion, CSV masivo y conector ERP local de demo para trabajadores.
- Versionado documental.
- Caducidades y alertas.
- Motor de requisitos simple.
- Dashboard.
- Exportación ZIP/Excel por plataforma mock/cliente.
- Conector demo local y exportacion manual mock.
- OCR con dropzone y alcance `auto`, `company`, `single_worker` o `multiple_workers`.
- Auditoría básica.

## 9. MVP 2

- Requisitos complejos por centro/actividad/puesto/riesgo.
- Semáforo por trabajador, empresa y plataforma.
- OCR asistido para fechas y tipo documental.
- Panel de transferencias.
- Alta controlada del catalogo de una plataforma comercial concreta cuando exista autorizacion y necesidad real.
- Conectores ERP reales contra APIs oficiales/autorizadas y mapeo de campos por tenant.

## 10. MVP 3

- API real donde exista documentación/autorización.
- RPA autorizada con Playwright para plataformas con permiso explícito.
- Reintentos, backoff, evidencias, comparación de estados.
- Validación externa periódica.

## 11. Criterios de aceptación iniciales

- Un usuario puede crear una empresa, un trabajador y subir documentos.
- El sistema calcula si el trabajador cumple requisitos de un centro/proyecto.
- El sistema alerta de documentos próximos a caducar.
- El sistema genera un paquete exportable para una plataforma concreta.
- El conector demo simula subida y estado externo.
- Toda operación queda auditada.
- No se almacenan credenciales en claro.
