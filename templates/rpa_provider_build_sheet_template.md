# Hoja de construccion RPA por proveedor

Proveedor:

Plataforma/familia:

Contrato tecnico:

## 1. Alcance autorizado

| Empresa local | CIF/NIF | Cuenta externa | Nombre externo | Estado |
| --- | --- | --- | --- | --- |
| | | | | |

## 2. Operaciones a construir

| Prioridad | Operacion | Entidad | Direccion | Aprobacion humana | Estado |
| ---: | --- | --- | --- | --- | --- |
| 1 | `upload_worker_document` | Documento trabajador | IKER -> proveedor | Si | Pendiente |
| 2 | `upsert_worker` | Trabajador | IKER -> proveedor | Si | Pendiente |
| 3 | `read_external_status` | Estado documental | proveedor -> IKER | No escritura | Pendiente |

## 3. Recorrido funcional

Describir el flujo con pantallas y señales estables, no con passwords ni datos personales.

### Login

- URL:
- Usuario tecnico o cuenta autorizada:
- Captcha/MFA:
- Resultado esperado tras login:

### Seleccion de empresa

- Pantalla:
- Senal de que la empresa ARM correcta esta activa:
- Que hacer si aparecen varias empresas:

### Operacion principal

- Area de la aplicacion:
- Como buscar/crear entidad:
- Campos requeridos:
- Validaciones visibles:
- Confirmacion de guardado:

## 4. Datos de prueba

Usar IDs locales de demo o datos anonimizados.

| Entidad local | ID local | Estado |
| --- | ---: | --- |
| Empresa | | |
| Trabajador | | |
| Documento | | |

## 5. Riesgos y modo asistido

- Captcha:
- MFA:
- Avisos legales:
- Cambios de formulario:
- Seleccion manual requerida:

## 6. Evidencia aceptada

- Estados.
- Timestamps.
- Hash de documentos.
- Mensajes de error redaccionados.

No guardar cookies, tokens, passwords, HAR, datos de terceros ni historiales medicos.

## 7. Criterio de terminado

- Manifiesto YAML creado.
- Mapeo de campos creado.
- Tests de dry-run.
- Preview operativo.
- Submit con aprobacion manual.
- Auditoria antes/despues.
- Evidencia minima redaccionada.
- Documentacion actualizada.
