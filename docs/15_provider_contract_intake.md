# 15 - Ingesta de contratos tecnicos de proveedores

Fecha: 2026-05-18.

## Objetivo

Convertir los contratos tecnicos de cada proveedor en configuracion implementable para conectores `connector_rpa_*`.

## Documentos esperados por proveedor

- Contrato tecnico o autorizacion expresa.
- Identificacion del proveedor y plataforma.
- Empresas autorizadas.
- Cuentas tecnicas o usuarios autorizados.
- Operaciones permitidas.
- Datos permitidos por operacion.
- Condiciones de uso.
- Persona de contacto tecnico.
- Procedimiento ante captcha, MFA, avisos o errores.
- Politica de evidencias.
- Politica de soporte ante cambios de formulario.

## Informacion minima para construir

### Identidad

- Nombre comercial.
- Host o hosts.
- URL de entrada.
- Entorno: produccion, pruebas o cliente.
- Plataforma/familia tecnica.

### Alcance

- Empresas ARM autorizadas.
- CIF/NIF de empresa si aplica.
- Centros/obras/clientes cubiertos.
- Si el usuario externo puede ver mas empresas, como distinguir la autorizada.

### Operaciones

Marcar por plataforma:

- Alta de trabajador.
- Edicion de trabajador.
- Baja/desactivacion de trabajador.
- Subida de documento de trabajador.
- Subida de documento de empresa.
- Subida de documento de maquinaria/vehiculo.
- Consulta de estado documental.
- Lectura de rechazos o requerimientos.
- Descarga de justificante o acuse.

### Datos

Por operacion:

- Campos obligatorios.
- Campos opcionales.
- Formato esperado.
- Catalogos: pais, tipo documento, puesto, centro, tipo formacion, tipo documento CAE.
- Reglas de caducidad.
- Tamaños maximos de fichero.
- Extensiones aceptadas.

### Interaccion

No hace falta definir cada boton como limite contractual. Si hace falta documentar el recorrido tecnico:

- Pantalla inicial tras login.
- Como seleccionar empresa/cliente/proyecto.
- Como llegar al formulario de la operacion.
- Como reconocer que estamos en la entidad correcta.
- Como confirmar que la operacion se ha guardado.
- Como leer errores o rechazos.

### Seguridad

- Si hay captcha/MFA.
- Si hay aviso legal de sesion.
- Si hay bloqueo por intentos.
- Si se permite navegador asistido.
- Limites horarios o de volumen.

## Salida esperada

Por cada proveedor se generaran:

- Ficha de contrato tecnico resumida.
- Manifiesto RPA YAML.
- Mapeo de campos IKER -> plataforma.
- Mapeo de tipos documentales.
- Tests de `dry_run`.
- Flujo de aprobacion.
- Riesgos conocidos.

## Ubicacion recomendada

- Contratos originales: `requisitos/autorizaciones/<proveedor>/`.
- Resumen versionado sin secretos: `docs/providers/<proveedor>_contract_summary.md`.
- Manifiesto: `backend/app/connectors/rpa_manifests/<proveedor>.yaml`.
- Mapeos: `backend/app/connectors/rpa_manifests/<proveedor>_mappings.yaml`.

No versionar contratos con secretos, passwords, cookies, tokens o datos personales innecesarios.
