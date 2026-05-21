# 27 - Superficies de validacion posterior por plataforma

Fecha: 2026-05-20.

## Objetivo

Despues de dar de alta, editar o subir informacion en una plataforma externa, el
Hub no puede dar la accion por valida solo por haber pulsado guardar. Muchas
plataformas dejan la accion en una cola de revision humana, notificaciones,
incidencias, rechazos o estados pendientes.

Este mapa identifica, a partir de capturas tecnicas redaccionadas, donde debe
mirar cada conector para confirmar una escritura o detectar que queda pendiente
de validador.

No contiene credenciales, cookies, tokens, cuerpos HTTP, HTML, HAR, screenshots
ni valores de filas personales. Los endpoints observados se tratan como evidencia
tecnica redaccionada, no como contrato API.

## Contrato operativo

Una escritura externa solo es valida si cumple todo:

- Existe auditoria previa con operacion, entidad local y cuenta externa.
- La accion fue autorizada y ejecutada en el contexto plataforma+empresa
  correcto.
- Hay lectura posterior positiva en una superficie de trabajador, documento,
  pendiente, notificacion, incidencia o acceso.
- Si la lectura posterior no confirma la accion, el estado debe quedar como
  `submitted_external_pending_readback`.

## Implementacion

API:

```http
GET /api/v1/platform-maps/validation-surfaces
```

Script:

```powershell
python scripts\build_platform_validation_surface_map.py
```

Artefactos:

- `artifacts/platform-validation-surfaces/platform_validation_surfaces.redacted.json`
- `artifacts/platform-validation-surfaces/platform_validation_surfaces.redacted.csv`
- `artifacts/platform-validation-surfaces/platform_validation_surfaces_summary.redacted.md`

## Resultado ARM local

Ejecucion sobre `artifacts/platform-captures/`:

- Capturas vistas: 36.
- Capturas ARM actuales usadas: 18.
- Plataformas actuales detectadas: 7.
- Superficies detectadas: 129.

Resumen por plataforma:

- 6conecta: trabajador, documentacion, homologacion/pendientes,
  notificaciones y accesos. La lectura posterior debe empezar por `Empleados`
  y `Documentos`, y luego revisar `Homologacion`, `notification-summary` como
  evidencia tecnica y `Consulta accesos`.
- e-coordina: trabajador, documento, notificacion, incidentado y acceso. La
  evidencia mas fuerte esta en `Documentacion -> Solicitudes de documentacion`,
  con columnas como trabajador, documento, estado, caducidad e incidentado.
- Nomio: trabajadores, avisos/notificaciones e incidencias. Debe revisarse
  `AvisosAutomaticos`, `trabajadores`, `incidencias` e `incidenciasmes`.
- Timenet: trabajadores, gestion de incidencias y estado global. Debe revisarse
  la zona de trabajadores y la cola de incidencias despues de una accion.
- Validate: solo hay evidencia tecnica minima de listas/modelos de companias y
  trabajadores. Falta una captura interna profunda antes de tratarlo como
  readback confirmado.
- Vitaly CAE: hay senales de acceso bloqueado/incidencia en respuestas
  observadas, pero falta una captura interna profunda posterior a seleccion de
  cliente.
- CTAIMA / CTAIMA CAE: las capturas persistidas actuales no contienen bandejas
  internas ni notificaciones profundas. Aunque el operador llego a entrar en la
  plataforma, el Hub todavia necesita una captura redaccionada posterior a la
  seleccion de empresa para mapear pendientes, notificaciones, validaciones,
  rechazos y estados documentales.

## Uso por conectores

Cada conector de escritura debe declarar un plan de lectura posterior:

1. Buscar entidad principal: trabajador, empresa, documento o equipo.
2. Revisar estado documental o de alta.
3. Revisar cola de pendientes/validacion.
4. Revisar notificaciones/avisos.
5. Revisar incidencias/rechazos.
6. Revisar acceso/estado global si la plataforma lo separa.

Si el plan solo contiene endpoints observados y no contiene superficie UI
confirmada, el conector no debe automatizarlo como API privada. Debe pedir una
captura read-only profunda mediante la pasarela humana.
