# 22 - Mapeo e-coordina estados documentales

Fecha: 2026-05-18.

## Alcance

Se ejecuto una captura live de solo lectura sobre la cuenta ARM / ARITEX ya autorizada en el paquete `iker_arm_base_legal_operativa_2026-05-18.zip`.

No se guardaron credenciales, cookies, tokens, HAR, capturas, cuerpos HTTP ni valores de filas con personas, empresas o documentos.

## Resultado

Login:

- URL: `https://v5.e-coordina.com/aritex`.
- Resultado: `login_likely_success`.
- Captcha: `false`.
- MFA/OTP: `false`.
- Contexto: `e-coordina - ARITEX`.

Navegacion read-only confirmada:

1. `itemId=documentacion`, texto visible `Documentacion`.
2. `itemId=documentacion_solicitud`, texto visible `Solicitudes de documentacion`.

Pantalla documental confirmada:

- Modulo: solicitudes de documentacion.
- Rejilla principal con columna de estado real:
  - `Documento` / `dataIndex=documento`.
  - `Estado` / `dataIndex=documentacion_estado`.
  - `Empresa` / `dataIndex=empresa`.
  - `Trabajador` / `dataIndex=trabajador`.
  - `Centro` / `dataIndex=centro`.
  - `Puesto` / `dataIndex=puesto`.
  - `Proyecto` / `dataIndex=proyecto`.
  - `Trabajo` / `dataIndex=trabajo`.
  - `Coordinacion` / `dataIndex=contratacion`.
  - `Maquinaria` / `dataIndex=maquinaria`.
  - `Vehiculo` / `dataIndex=vehiculo`.
  - `Tipo doc.` / `dataIndex=documento_tipo`.
  - Fechas: solicitado, limite, cumplimentado, verificado, emision y caducidad.

Lectura real de estados agregados:

- Campo leido: `documentacion_estado`.
- Valores detectados en la cuenta probada:
  - `Validado`: 5.
  - `Caducado`: 4.
- Normalizacion interna:
  - `Validado` -> `accepted`.
  - `Caducado` -> `expired_external`.

## Integracion

El conector `backend/app/connectors/rpa/e_coordina/readonly.py` queda actualizado para abrir esa ruta en modo solo lectura y devolver:

- `navigation_actions`.
- `pages[].grid_columns`.
- `pages[].status_column_counts`.
- `external_status_summary.mode = readonly_grid_status_counts` cuando hay conteo de columna real.
- `external_status_summary.column_status_counts`.

La persistencia por documento local sigue desactivada porque todavia no hay una regla aprobada que enlace una fila externa concreta con `document_version_id` sin almacenar datos personales externos.

## Conclusion tecnica

Si: con la autorizacion actual y mientras no aparezcan captcha/MFA/avisos, el sistema es capaz de recoger estados reales agregados de e-coordina desde `documentacion_estado`.

Todavia no debe persistir estados por documento/trabajador hasta definir el enlace minimo y auditable entre fila externa y documento local.
