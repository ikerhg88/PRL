# 14 - Alcance de datos para plataformas externas

Fecha: 2026-05-18.

## Regla central

El alcance se controla por datos autorizados, no por botones de la interfaz externa.

Esta regla aplica a plataformas externas. En la plataforma propia, el Hub IKER
PRL/CAE, las altas, cambios y correcciones se ejecutan como escrituras internas
en vivo cuando el usuario lo pide y el permiso local lo permite. Deben mantener
auditoria y separacion por tenant/empresa, pero no requieren `dry_run` externo.

Una automatizacion RPA solo puede actuar sobre datos que cumplan todas estas condiciones:

1. Pertenecen al tenant autenticado.
2. Pertenecen a una empresa local autorizada.
3. La empresa esta vinculada a la cuenta externa de plataforma.
4. La operacion esta incluida en el contrato tecnico o autorizacion expresa.
5. El usuario aprobador tiene permiso local para esa empresa y operacion.

## Entidades autorizables

- Empresa.
- Centro de trabajo.
- Proyecto/obra.
- Trabajador.
- Maquinaria/equipo.
- Vehiculo.
- Documento y version documental.
- Estado documental externo.

## Tabla de vinculacion

Cada cuenta externa debe tener una configuracion local:

- `tenant_id`.
- `company_id`.
- `platform_account_id`.
- `external_platform_id`.
- `external_company_name`.
- `external_company_id` si existe.
- `allowed_entity_types`.
- `allowed_operations`.
- `mode`: `manual_export`, `authorized_rpa`, `api_official`.
- `dry_run`.
- `manual_approval_required`.

## Politica de seleccion de empresa externa

Si la plataforma muestra varias empresas:

- La RPA debe seleccionar solo la empresa externa vinculada.
- Si la empresa no se puede identificar de forma estable, el job pasa a `human_action_required`.
- Si aparecen datos de empresas no vinculadas, no se capturan ni se usan.
- La evidencia no debe incluir listados de terceros.

## Politica de trabajadores

Se permite enviar o actualizar solo trabajadores locales cuyo `company_id` coincida con la cuenta externa.

Antes de enviar:

- Nombre y apellidos revisados.
- Identificador personal solo si es necesario para CAE y esta autorizado.
- NAF solo si es imprescindible y autorizado.
- Aptitud medica limitada a estado, emision, caducidad, proveedor y restricciones preventivas necesarias.
- No se estructura diagnostico, pruebas medicas ni historial clinico.

## Politica documental

Se permite subir solo versiones documentales aprobadas o marcadas como listas para transferencia.

Cada documento debe tener:

- Tipo documental local.
- Entidad local vinculada.
- Version inmutable.
- SHA-256.
- Nombre de fichero seguro.
- Caducidad local si aplica.
- Mapeo de tipo externo para esa plataforma.

## Aprobacion

La escritura externa es una operacion automatizada del producto y requiere:

- Preview generado.
- Usuario aprobador.
- Comentario de aprobacion.
- Lista exacta de entidades aprobadas.
- Auditoria antes de ejecutar.
- Auditoria despues de ejecutar con resultado y evidencia minima.

## Errores de alcance

El job debe fallar antes de abrir navegador si:

- La empresa local no esta vinculada a la cuenta externa.
- El usuario no tiene permiso.
- La entidad pertenece a otra empresa.
- El tipo documental no esta mapeado.
- La operacion no esta autorizada.

El job debe detenerse durante la navegacion si:

- La plataforma muestra una empresa externa no esperada.
- Aparece un control que requiere intervencion humana.
- Cambia el flujo previsto de forma que impide confirmar el alcance.
- Se detecta riesgo de escribir sobre datos de terceros.
