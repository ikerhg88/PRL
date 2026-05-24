# 28 - Principios, objetivos y revision de refactor

Fecha: 2026-05-23.

## Objetivo principal

Construir un Hub PRL/CAE propio para ARM que sea la fuente unica de verdad de
empresa, trabajadores, documentos, caducidades y evidencias, y que pueda operar
contra multiples plataformas externas por contexto:

`plataforma + empresa externa + centro/proyecto`.

El resultado esperado no es solo almacenar documentos. El producto debe decir:

- que datos tiene ARM;
- que ve cada plataforma externa;
- que pide cada plataforma;
- que falta en el Hub;
- que se puede subir o actualizar;
- que accion se ha ejecutado;
- que lectura posterior confirma el resultado.

## Principios basicos del proyecto

1. **Hub primero**
   ARM mantiene sus datos y documentos en el Hub. Las plataformas externas son
   destinos o fuentes de estado, no la fuente principal.

2. **Contexto operativo real**
   Una plataforma no es solo una URL. La unidad operativa es plataforma, cuenta,
   empresa externa, centro/proyecto y estado activo/inactivo.

3. **Lectura antes que escritura**
   No se debe escribir en una plataforma si antes no se ha leido el contexto y
   comprobado si el trabajador/documento ya existe o si realmente lo pide.

4. **Escritura confirmada**
   Una escritura solo cuenta como valida si hay lectura posterior que confirme el
   alta, cambio o subida documental.

5. **No inventar integraciones**
   No se inventan endpoints, selectores, rutas internas ni estados externos. Si
   falta evidencia, el sistema debe bloquear y pedir captura/mapeo.

6. **Mapeo completo de plataformas**
   Todas las plataformas activas deben tener mapeadas sus superficies de lectura,
   campos editables, equivalencias documentales, estados externos, rutas de
   lectura posterior y helpers necesarios para poder leer y escribir en cada
   contexto autorizado.

7. **Trazabilidad completa**
   Toda accion externa debe tener preview, aprobacion, auditoria antes/despues,
   evidencias minimas y resultado de lectura posterior.

8. **Privacidad y minimizacion**
   Guardar solo datos necesarios para PRL/CAE. En vigilancia de salud, aptitud y
   fechas, no historiales clinicos.

9. **Modularidad por plataforma**
   Cada plataforma tiene su lector/helper independiente. Un avance en CTAIMA no
   debe romper e-coordina, 6conecta o exportacion manual.

10. **Operativa entendible**
    El usuario debe ver estados accionables, no codigos tecnicos: existe, falta,
    pedido por plataforma, disponible en Hub, bloqueado por mapeo, pendiente de
    validacion externa.

## Objetivos funcionales refinados

### ARM

- Ficha de empresa completa.
- Trabajadores con DNI como identificador unico operativo.
- Documentos versionados, con fecha de emision/caducidad y SHA-256.
- Tipos documentales normalizados y editables.
- Baja/reactivacion de trabajadores sin borrado destructivo.

### Plataformas

- Listado de contextos activos/inactivos.
- Filtros por plataforma, empresa externa, centro, conexion, lectura, escritura,
  helper y avisos.
- Boton `Analizar ahora`.
- Boton `Preparar 100%` que lanza lo necesario: lectura, captura, mapeo o
  pasarela humana.
- Estado visible del helper especifico.

### Notificaciones

- Avisos solo de plataformas activas.
- Peticiones externas normalizadas.
- Evidencias internas pendientes.
- Filtros por fecha, severidad, origen, plataforma y visibilidad.
- Anular/restaurar avisos sin borrar datos.
- Plan de actualizacion masiva desde Hub: altas pendientes, documentos pedidos,
  previews listos, bloqueos y pasarelas recomendadas.

### Alta y actualizacion

- Alta de trabajador en plataforma si no existe.
- Bloqueo automatico si ya existe.
- Subida de documentos de trabajador o empresa si la plataforma los pide.
- Actualizacion de datos solo con preview y lectura posterior.

## Estado tecnico actual

Fortalezas:

- Backend FastAPI con modelos amplios, Alembic, tests y RBAC.
- Frontend operativo ya reducido a ARM, Plataformas, Añadir trabajador,
  Notificaciones y Pasarela RPA.
- Versionado documental inmutable.
- Pasarela humana con navegador visible y credenciales resueltas en servidor.
- Registro de conectores RPA por plataforma.
- `6conecta` tiene helper live real para alta de trabajador.
- Estado observado de plataformas ya existe y Notificaciones lo consume.

Riesgos/deuda:

- Las lecturas externas aun no capturan todos los requisitos documentales fila a
  fila en todas las plataformas.
- Las subidas documentales no tienen todavia el mismo nivel de helper/readback
  que el alta de trabajador.
- La activacion sigue mezclando algunas decisiones por plataforma/manifiesto y
  por cuenta/contexto; debe quedar centrada en contexto.
- Falta un comparador unico Hub vs plataforma que alimente todas las pantallas.
- Hay deuda de naming y estados tecnicos que todavia aparecen en algunas capas.
- Los jobs externos aun no estan plenamente desacoplados en una cola duradera.

## Propuestas de refactor por prioridad

### Prioridad 1 - Comparador operativo

Crear un servicio unico `platform_reconciliation` que tome:

- datos ARM;
- `PlatformObservedEntity`;
- `PlatformObservedDocumentRequest`;
- registros `WorkerPlatformRegistration`;
- paths/helpers de escritura;

y devuelva una matriz accionable por contexto:

- trabajador existe/no existe;
- documento pedido/no pedido;
- documento disponible/no disponible en Hub;
- escritura posible/bloqueada;
- accion recomendada.

### Prioridad 2 - Documentos externos como flujo fuerte

Unificar subida documental con `exchange preview/submit`:

- no usar transferencias documentales directas sin cuenta;
- exigir `account_proposal_id`;
- exigir preview;
- exigir helper/path aprobado para live;
- persistir estado externo solo si hay readback.

### Prioridad 3 - Contexto como unidad de configuracion

Crear configuracion por cuenta/contexto:

- activo/inactivo;
- intervalo de revision;
- ultima lectura;
- siguiente lectura;
- responsable;
- bloqueo manual;
- comentario operativo.

### Prioridad 4 - Lectores especificos

Completar, una a una, capturas de lectura para plataformas activas:

1. CTAIMA.
2. 6conecta.
3. e-coordina.
4. Resto del Excel actual.

Cada lector debe entregar entidades y peticiones documentales normalizadas.

### Prioridad 5 - UX de acciones

Desde una notificacion externa, el operador deberia poder:

- abrir ficha ARM relacionada;
- ver documento disponible;
- preparar subida;
- abrir pasarela si falta mapeo, lectura posterior o evidencia aprobada;
- ver historico de intentos y lectura posterior.

## Cambios hechos en esta revision

- `/notifications` carga `/api/v1/platform-observations/document-requests`.
- Las peticiones externas observadas aparecen como avisos de origen
  `Lectura externa normalizada`.
- Si el Hub tiene documento equivalente, la accion indica preparar subida con
  preview y aprobacion.
- Si falta documento equivalente, la accion indica cargarlo o crear tipo
  documental.
- `platform_reconciliation` queda como comparador operativo inicial: une
  manifests, cuentas/contextos, schedules, superficies de lectura,
  observaciones normalizadas, helpers live, operaciones de escritura y
  `platform_write_paths`.
- `/api/v1/platform-observations/operational-map` expone esa matriz para que
  `/platforms` no dependa de calculos parciales de UI.
- `/platforms` muestra "Mapeadas read/write" y blockers por fila: falta URL,
  falta superficie, falta primera lectura, helper pendiente, operaciones core
  sin mapear o paths pendientes de revision.
- Se anadio una regresion backend para asegurar que un contexto solo aparece
  completo si lectura y escritura tienen evidencias suficientes.
- `platform_mass_update` anade la capa de producto para operar en lote: planifica
  acciones desde Hub, separa altas y documentos, ejecuta solo en dry-run por
  defecto y crea pasarelas de captura cuando la accion no esta lista.
- `/notifications` incorpora el panel `Actualizacion masiva` para recalcular y
  preparar actualizaciones sin salir del visor operativo.

## Criterio para redefinir alcance

Si se quiere reducir alcance para llegar antes a valor real:

1. ARM completo.
2. CTAIMA completo en lectura.
3. 6conecta completo en alta trabajador.
4. Subida documental en una unica plataforma piloto.
5. Exportacion manual como fallback para el resto.

Si se quiere ampliar alcance:

1. Normalizar todas las plataformas activas.
2. Implementar cola de jobs.
3. Añadir portal de validacion documental para terceros.
4. Añadir reporting/auditoria avanzada.
