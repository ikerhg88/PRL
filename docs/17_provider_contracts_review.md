# 17 - Revision de contratos tecnicos en requisitos

Fecha: 2026-05-18.

## Fuente revisada

Carpeta:

```text
requisitos/iker_contratos_plataformas_max_scope_2026-05-18/
```

El paquete contiene borradores de autorizacion tecnica y configuracion implementable generados desde el Excel de cuentas. No son, por si solos, contratos firmados finales. El propio paquete exige autorizacion firmada antes de permitir escrituras externas.

## Resumen cuantitativo

- Cuentas procesadas: 115.
- Familias/plataformas generadas: 47.
- Cuentas activas en origen: 91.
- Cuentas no activas en origen: 24.
- Manifiestos RPA encontrados: 47.
- Contratos tecnicos Markdown encontrados: 45.
- Contratos tecnicos DOCX encontrados: 44.
- Cuentas ARM en manifiestos: 34.
- Cuentas ARM activas: 34.
- Plataformas con host o URL pendiente: 16.
- Ficheros de mapeo con catalogos externos pendientes: 47.
- Passwords en claro detectadas por la validacion del paquete: 0.

## Seguridad y alcance

Todos los 47 manifiestos revisados declaran:

- `requires_signed_authorization: true`.
- `dry_run_default: true`.
- `manual_approval_required: true`.
- `rpa_assisted_on_captcha_mfa_or_notice: true`.

Esto encaja con las reglas del proyecto: el paquete sirve para preparar manifiestos y previews, pero no habilita escrituras automaticas directas.

Operaciones cubiertas en todos los manifiestos:

- `sync_company_profile`.
- `upsert_worker`.
- `deactivate_worker`.
- `upload_worker_document`.
- `upload_company_document`.
- `upload_machine_vehicle_document`.
- `read_external_status`.
- `read_rejections`.
- `download_receipt`.

## Plataformas ARM detectadas

| Plataforma | Cuentas ARM | Activas | Host pendiente | Hosts |
| --- | ---: | ---: | ---: | --- |
| 6conecta | 1 | 1 | 0 | www.6conecta.com |
| CTAIMA / CTAIMA CAE | 3 | 3 | 0 | www.ctaimacae.net |
| Dokyfy | 2 | 2 | 0 | www.dokyfy.net |
| Folyo | 1 | 1 | 0 | seat.folyo.es |
| IEDOCE | 2 | 2 | 0 | www.gestion.iedoce.com |
| Integra ASEM Webservices | 2 | 2 | 0 | integra.asemwebservices.es |
| Koordinatu | 3 | 3 | 0 | agrisolutions.koordinatu.com, bellota.koordinatu.com, cieautomotive.koordinatu.com |
| Metacontratas | 1 | 1 | 0 | www.metacontratas.com |
| Nomio | 1 | 1 | 0 | app.nomio.io |
| Quioo / QUIO | 1 | 1 | 0 | quioo.es |
| Quironprevencion | 1 | 1 | 1 | PENDIENTE_HOST |
| SGS Gestiona | 1 | 1 | 0 | sgs.sgs-gestiona.es |
| Sarenet | 1 | 1 | 1 | PENDIENTE_HOST |
| SmartOSH | 2 | 2 | 0 | gestamp-abrera.smartosh.com, tiautomotive.smartosh.com |
| Timenet | 1 | 1 | 0 | timenet.gpisoftware.com |
| UCAE | 1 | 1 | 0 | u5.ucae.es |
| Validate | 1 | 1 | 0 | secure.validate.network |
| Vitaly CAE | 1 | 1 | 0 | cae.vitaly.es |
| e-coordina | 6 | 6 | 0 | v5.e-coordina.com |
| eGestiona / Subcontratas | 2 | 2 | 0 | fagorederlan.egestiona.es, faurecia.egestiona.com |

## Plataformas con bloqueo por host o URL pendiente

Estas familias no se deben convertir en conector ejecutable hasta resolver URL/host de entrada:

- Adevinta - pendiente URL/host.
- Amazon - pendiente URL/host.
- Arania - pendiente URL/host.
- BIDEGI - pendiente URL/host.
- Correos - pendiente URL/host.
- El Corte Ingles.
- Google Gmail.
- HILTI - pendiente URL/host.
- Hubwoo.
- Iberdrola.
- Microsoft.
- Pendiente URL/host no identificado.
- Prevengos.
- Rockwell Automation.
- Sarenet.
- ULMA - pendiente URL/host.

En ARM afecta a:

- Quironprevencion: 1 cuenta ARM con `PENDIENTE_HOST`.
- Sarenet: 1 cuenta ARM con `PENDIENTE_HOST`.

## Plataformas con minimizacion reforzada

Estas requieren mayor control de datos por naturaleza laboral/sensible:

- Nomio.
- Quironprevencion.
- Timenet.

Politica aplicable:

- No historiales clinicos.
- No diagnosticos.
- Solo aptitud laboral, emision/caducidad, proveedor y restricciones preventivas necesarias.
- Evidencia minima redaccionada.

## Plataformas auxiliares o no puramente CAE

Estas aparecen en el paquete, pero requieren revision funcional antes de tratarlas como conectores CAE:

- El Corte Ingles.
- Google Gmail.
- Hubwoo.
- Iberdrola.
- Microsoft.
- Rockwell Automation.
- Sarenet.
- SPRI Enpresa Digitala.

Decision recomendada: mantenerlas como `auxiliary_platform_review_required` y no priorizarlas para el primer ciclo de conectores CAE.

## Carencias detectadas

1. Todos los mapeos documentales siguen con `PENDIENTE_CATALOGO_PLATAFORMA` o `pending_platform_confirmation`.
2. El tamano maximo de fichero aparece como `PENDIENTE_CONFIRMAR_EN_DRY_RUN` en los mapeos.
3. Los manifiestos proponen operaciones de maximo alcance; falta cerrar que operaciones quedan firmadas por proveedor/cuenta.
4. No hay selectores tecnicos versionados validados contra captura para ejecutar RPA real.
5. No hay confirmacion de catalogos externos por plataforma: tipos documentales, puestos, centros, estados, formatos.
6. Hay 16 familias con host o URL pendiente.
7. Faltan ficheros de contrato `01` en `pendiente_url_host__pendiente_url_host_no_identificado` y `webcontratas_irizar__webcontratas_irizar_e_mobility`.
8. Falta DOCX de contrato en `adevinta_pendiente__adevinta_pendiente_url_host`.

## Prioridad recomendada para ARM

Primera prioridad, porque ya tienen cuenta ARM activa, host estable y encajan con el mapa estructural/imports existentes:

- e-coordina.
- 6conecta.
- Validate.
- Timenet.
- Nomio, con minimizacion reforzada.
- Vitaly CAE.

Segunda prioridad, porque tienen cuenta ARM activa pero requieren revisar login, catalogos o controles:

- CTAIMA / CTAIMA CAE.
- Metacontratas.
- UCAE.
- eGestiona / Subcontratas.
- Dokyfy.
- IEDOCE.
- Folyo.
- SGS Gestiona.
- SmartOSH.
- Koordinatu.
- Integra ASEM Webservices.
- Quioo / QUIO.

Bloqueadas por datos pendientes en ARM:

- Quironprevencion.
- Sarenet.

## Como usar estos contratos en el producto

1. Ingestar cada `03_rpa_manifest.yaml` como configuracion deshabilitada.
2. Ingestar cada `04_mappings.yaml` como propuesta `pending_review`.
3. Asociar cada cuenta a tenant, empresa y `PlatformAccount`.
4. Cruzar los campos del manifiesto con `platform_discovered_labels` y aprobar solo coincidencias revisadas.
5. Crear previews de intercambio, sin navegador o con navegador solo en lectura, hasta cerrar catalogos.
6. Habilitar submit solo cuando existan:
   - autorizacion firmada;
   - host estable;
   - catalogo documental externo confirmado;
   - mapeos aprobados;
   - pruebas `dry_run`;
   - aprobacion manual por job;
   - auditoria antes/despues.

## Conclusion

El paquete es util para construir la capa de configuracion de conectores, especialmente manifiestos, cuentas saneadas y mapeos pendientes. No es suficiente para activar escrituras externas reales. El siguiente paso tecnico seguro es importar estos manifiestos como propuestas deshabilitadas y crear una UI/API de revision para convertirlos en mapeos aprobados por plataforma y cuenta.
