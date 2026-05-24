# 27 - Plan operativo para lectura y actualizacion de plataformas

Fecha: 2026-05-23.

## Objetivo

El Hub debe centralizar los datos reales de ARM y mantener una vista operativa por
plataforma + empresa externa + centro de trabajo. Cada contexto activo debe poder:

- leer trabajadores, documentos, requisitos y estados externos;
- detectar que pide la plataforma;
- comparar lo pedido con los documentos y datos disponibles en el Hub;
- preparar altas, actualizaciones y subidas documentales;
- ejecutar escritura solo con mapeo/helper aprobado, auditoria previa/posterior y lectura de confirmacion;
- bloquear y pedir pasarela humana si aparece captcha, MFA, aviso legal, sesion duplicada o mapeo incompleto.

## Principios de implementacion

- No se inventan endpoints, rutas internas ni selectores de plataformas comerciales.
- Todo flujo externo parte de `dry_run` y `manual_approval_required`.
- Las credenciales se resuelven desde referencias cifradas y no se imprimen ni se guardan en logs.
- Cada escritura debe tener:
  1. lectura previa y control de duplicados;
  2. preview de campos/ficheros;
  3. aprobacion humana;
  4. ejecucion por helper especifico aprobado;
  5. lectura posterior;
  6. auditoria antes y despues.
- Si falta algun punto, el estado correcto es bloqueado, no exito simulado.

## Fase 1 - Estado observado normalizado

Implementado en esta iteracion:

- `PlatformObservedEntity`: entidades vistas en plataforma, por cuenta/contexto.
- `PlatformObservedDocumentRequest`: requisitos o estados documentales observados en plataforma.
- API `/api/v1/platform-observations/*` para consultar resumen, entidades y peticiones documentales.
- Servicio `platform_reconciliation`: mapa unico por contexto que cruza
  superficies de lectura, observaciones normalizadas, paths de escritura,
  helpers live y operaciones core.
- API `/api/v1/platform-observations/operational-map` para que el frontend use
  un estado unico de lectura/escritura por plataforma + empresa + centro.
- Sincronizacion desde capturas de solo lectura de pasarela RPA.
- `/notifications` consume `PlatformObservedDocumentRequest` como avisos accionables
  de origen "Lectura externa normalizada".
- `/platforms` consume el mapa operativo para mostrar lectura, escritura,
  blockers, paths aprobados/pendientes, peticiones externas y estado de mapeo
  read/write.

Resultado esperado:

- `/platforms` podra consultar datos leidos persistidos.
- El sistema dejara de depender de textos sueltos dentro de `PlatformReviewRun.evidence_json`.
- Una fila solo se marca como mapeada read/write cuando existen lectura,
  superficies, helper live, operaciones core listas y paths aprobados con
  lectura posterior prevista.

## Fase 2 - Lectores por plataforma

Para cada plataforma activa:

- definir lector autorizado y de solo lectura;
- identificar modulos visibles: trabajadores, empresa, documentos, pendientes, rechazos y caducidades;
- guardar solo datos operativos necesarios en las tablas normalizadas;
- asociar cada fila con trabajador, empresa, documento o tipo documental del Hub cuando sea posible;
- dejar `confidence` bajo si el emparejamiento no es seguro.

Orden recomendado:

1. CTAIMA, porque ya hay captura real de trabajadores y contexto SOFIDEL/GRUPO.
2. 6conecta, porque ya existe helper live para alta de trabajador.
3. e-coordina, porque ya hay piloto de solo lectura.
4. Resto de plataformas activas importadas desde el Excel de credenciales.

## Fase 3 - Comparador Hub vs plataforma

Con las observaciones normalizadas:

- detectar trabajador ya existente antes de preparar alta;
- detectar trabajador ausente en una plataforma activa;
- detectar documento pedido por plataforma y disponible en Hub;
- detectar documento pedido pero no disponible en Hub;
- detectar documento subido pero rechazado/caducado en plataforma;
- detectar datos de trabajador o empresa divergentes.

Este comparador alimentara:

- `/platforms`: estado operativo por contexto;
- `/assign-worker`: destinos disponibles, existentes o bloqueados;
- `/notifications`: avisos accionables;
- futuras colas automaticas cada 12 horas.

Implementado como primera version:

- `platform_mass_update`: genera un plan de acciones desde el Hub por contexto
  activo.
- `POST /api/v1/exchange/mass-update/plan`: devuelve altas de trabajadores que
  faltan y documentos pedidos por plataforma que ya tienen version disponible en
  Hub.
- `POST /api/v1/exchange/mass-update/submit`: prepara jobs en bloque para las
  acciones con preview y crea pasarelas `capture_write_screen` para acciones
  bloqueadas por mapeo, helper o datos locales.
- `/notifications` muestra `Actualizacion masiva` con acciones propuestas,
  previews listos, bloqueos y pasarelas recomendadas.
- La ejecucion masiva no escribe fuera si falta preview, aprobacion, helper
  especifico o lectura posterior.

## Fase 4 - Escritura documental con el mismo nivel que alta trabajador

La subida de documentos debe pasar por el mismo contrato que `upsert_worker`:

- `POST /exchange/{account}/preview` prepara documento/campo/fichero;
- `POST /exchange/{account}/submit` ejecuta solo si el preview esta listo;
- `/transfers` no debe persistir estado externo si no hay lectura posterior;
- cada helper especifico debe devolver `confirmed_external`, `already_exists_external`,
  `blocked_mapping_review_required` o `blocked_live_adapter_missing`.

## Fase 5 - Helpers especificos

Cada plataforma tendra paquete independiente:

`backend/app/connectors/rpa/<plataforma>/write.py`

Operaciones minimas:

- `test_connection`;
- `sync_catalog` o lectura de requisitos;
- `upsert_worker`;
- `upload_worker_document`;
- `upload_company_document`;
- `readback_worker`;
- `readback_document_status`.

Una plataforma se considera operativa solo cuando:

- el helper especifico existe;
- las rutas editables tienen evidencia y revision;
- los mapeos estan aprobados;
- una prueba real autorizada confirma lectura posterior.

## Fase 6 - UX final

Pantallas principales:

- ARM: datos propios, trabajadores, documentos internos, tipos documentales y versiones.
- Plataformas: contextos plataforma + empresa + centro, activacion, ultima lectura, helper, mapeos y boton "Poner operativa".
- Añadir trabajador: trabajador seleccionado, plataformas donde ya existe, destinos disponibles, documentos que se subirian y bloqueos.
- Notificaciones: peticiones externas accionables con filtros, ocultar anteriores a fecha, anular/descartar y lanzar accion.

## Fase 7 - Jobs

La revision automatica cada 12 horas debe ejecutar solo contextos activos:

- lectura de plataforma;
- sincronizacion de observaciones;
- comparacion contra Hub;
- generacion de notificaciones;
- nunca escritura automatica sin aprobacion.

## Validacion

Cada iteracion debe incluir:

- migracion si cambia modelo;
- tests backend enfocados;
- test frontend si cambia UX;
- `make test` o suite equivalente antes de declarar terminado;
- actualizacion de esta documentacion si cambia el flujo.
