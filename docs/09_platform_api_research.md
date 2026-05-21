# Investigacion de plataformas CAE e integraciones

Fecha de investigacion inicial: 2026-05-16.
Revision tecnica API/documentacion: 2026-05-17.

Objetivo: mantener un catalogo tecnico de plataformas CAE principales para priorizar conectores futuros sin inventar endpoints, selectores ni contratos privados. Ninguna integracion comercial queda activa por defecto. Solo se permite `manual_export` con `connector_manual_export` y siempre sin escritura externa.

## Criterio de catalogacion

- `official_api_public_product`: el proveedor anuncia API/documentacion o portal publico, aunque el detalle pueda requerir cuenta/licencia.
- `api_declared_private_docs`: el proveedor declara API/integracion, pero no hay referencia tecnica publica suficiente.
- `service_web_documented_commercially`: la web publica describe mecanismos de servicio web/URL/sincronizacion.
- `no_public_api_found`: plataforma relevante, sin contrato API publico localizado.
- `konvergia_network`: red interplataforma. No sustituye un contrato directo con cada plataforma.

## Hallazgos por plataforma

| Plataforma | Estado API | Evidencia publica | Decision en producto |
| --- | --- | --- | --- |
| Dokify | API oficial anunciada | La pagina de API publica funcionalidades sobre Checkin, Employee, Machine, Company, Document y User, y habla de referencias, ejemplos y buscador. | Catalogada; preparar futuro `connector_api_dokify` solo con licencia y documentacion oficial. |
| Nalanda Global | Integracion/API declarada | La pagina CAE menciona integracion informatica con ERP; el status publico separa "CAE Construction (API)". | Catalogada; pedir documentacion tecnica de API y credenciales de sandbox. |
| Konvergia | Red interplataforma | Nalanda/Konvergia describen subida unica y distribucion a plataformas asociadas; Konvergia declara que siete plataformas CAE participaron en la red. | Catalogada como red, no como API operativa; evaluar alta contractual. |
| CTAIMA / Twind | Portal de desarrollador visible | `developers.ctaima.com` publica catalogo de APIs/productos y niveles de peticiones mediante Azure API Management. | Catalogada; solicitar cuenta de desarrollador y producto API concreto. |
| 6conecta | API declarada | La web CAE declara API e integraciones con control de accesos, compras, autenticacion y BI; tambien declara integracion con Konvergia. | Catalogada; pedir referencia tecnica privada. |
| Metacontratas | Integracion declarada | La web describe plataforma CAE y la guia 2026 habla de conectividad/integracion avanzada. | Catalogada; sin API tecnica publica, solo manual export hasta contrato. |
| e-coordina | Servicio web/URL/sincronizacion descritos | La pagina de integracion describe servicio web, salida CSV/JSON/XML, altas/bajas y sincronizaciones con sistemas externos. | Catalogada; posible primer API cuando haya contrato y WSDL/OpenAPI real. |
| EcoGestor CAE | API/web service declarados | EcoGestor declara integracion por APIs y web service para plataformas de acceso, barreras y tornos. | Catalogada; solicitar contrato tecnico. |
| eGestiona / eIntegra | API declarada | La web declara `eIntegra API` y `API eData Sync`. | Catalogada; solicitar contrato tecnico. |
| UCAE | Konvergia declarada | La web describe UCAE Empresas/Plus/control de accesos y una pagina de adhesion a Konvergia. | Catalogada; no API publica localizada. |
| SG Red | Konvergia/interoperabilidad declarada | La web describe gestion documental, control de accesos e interoperabilidad entre plataformas asociadas. | Catalogada; no API publica localizada. |
| Sicondoc / Construred | Plataforma relevante | La web describe documentacion CAE, control de accesos, trabajadores, maquinaria y vehiculos. | Catalogada; no API publica localizada. |
| Validate | Servicio Web declarado | La pagina CAE declara Servicio Web para consultar datos y situacion de acceso de trabajadores desde control de accesos. | Catalogada; posible integracion de consulta de estado cuando haya contrato. |
| tdoc | Plataforma relevante | tdoc publica plataforma CAE y centro de ayuda de tdoc Access; no contrato API publico. | Catalogada; no API publica localizada. |
| Obralia / Nalanda construccion | Integracion XML historica | Obralia declara XML desarrollado para integracion ERP en contexto Nalanda/constructoras. | Catalogada como referencia de obra/Nalanda; no integrar sin contrato moderno. |
| CoordinaPlus / Adding Plus | Integracion declarada | Coordinaplus declara integracion CAE con ERP/control de accesos. | Catalogada; no API publica localizada. |
| Quioo / Quironprevencion | Plataforma relevante | Quioo describe CAE avanzada, firma, CAE inversa y estados moviles. | Catalogada; no API publica localizada. |

## Matriz tecnica ampliada 2026-05-17

La siguiente matriz distingue entre:

- API oficial confirmada o declarada por el proveedor.
- Documentacion tecnica publica realmente localizada.
- Documentacion funcional/de usuario, que no equivale a contrato API.
- Integracion declarada sin especificacion publica.

No se han inventado endpoints, selectores, payloads, credenciales ni URLs privadas.

| Plataforma | API oficial | Documentacion tecnica publica | Superficie localizada | Decision |
| --- | --- | --- | --- | --- |
| Dokify | Si, pagina oficial API. | Pagina API publica; detalle operativo aparentemente gated/licenciado. | Checkin, Employee, Group, Client, Machine, Company, Document, User. | Prioridad alta cuando haya licencia, sandbox y referencia tecnica. |
| Nalanda Global | Si/declarada; componente API visible. | Pagina CAE + status publico con CAE Construction (API); sin OpenAPI/WSDL publico. | ERP integration, CAE Construction API, Konvergia. | Pedir documentacion API de CAE Construction. |
| Konvergia | No API publica localizada. | Documentacion funcional de red; servicio en cierre. | Red de transferencia, modos send/receive, panel de estado. | Referencia funcional, no dependencia operativa. |
| CTAIMA / Twind | Si, portal oficial de desarrollador. | Portal Azure API Management con APIs, productos, consola y limites; detalle requiere cuenta. | CTAIMACAE.net APIs, productos Standard/Extra/Advantage, consola. | Crear cuenta/contrato antes de cualquier conector. |
| 6conecta | API declarada; privada/no publicada. | Pagina comercial menciona API e integraciones; sin especificacion publica. | Control de accesos, compras, usuarios/autenticacion, BI. | Solicitar referencia privada. |
| Metacontratas | No API publica localizada. | Help center de usuario y pagina producto; no contrato API. | Panel de acceso unificado, subida multicliente, document types linked. | Manual export hasta contrato tecnico. |
| e-coordina | Si, servicio web declarado. | Pagina publica de integracion; sin WSDL/OpenAPI. | Servicio web, URL CSV/JSON/XML, altas de trabajadores/empresas/proyectos/trabajos, sincronizaciones. | Buena candidata para primer conector API si entregan contrato tecnico. |
| EcoGestor CAE | Web Service declarado. | Pagina producto declara Web Service; sin endpoints. | Integracion con barreras/tornos/control de accesos. | Solicitar especificacion. |
| eGestiona / eIntegra | API declarada. | Paginas eData Sync/API eData Sync; sin endpoints. | eAccess Sync, acreditaciones, documentos vinculados, SSL, SFTP. | Solicitar contrato API y modelo de campos. |
| UCAE | No API publica localizada. | Producto, UCAE Plus, Konvergia; no docs API. | Archivo documental, carga en otras plataformas, control de accesos. | Manual export. |
| SG Red | No API publica localizada. | Producto y articulo Konvergia; no docs API. | Gestion documental, carga de ficheros, red Konvergia. | Manual export. |
| Sicondoc / Construred | No API publica localizada. | Pagina de lanzamiento/funcional; no docs API. | Gestion documental, estado documental, control de accesos, contexto ERP Sicon. | Manual export. |
| Validate | Web Service declarado. | Pagina CAE declara Web Service de consulta; sin endpoints. | Consulta online de datos y situacion de acceso de trabajadores. | Solicitar especificacion Web Service. |
| tdoc | No API publica localizada. | Help center/manual tdoc Access; no docs API. | Consulta web de accesos/documentacion, bloqueo/forzado, export Excel. | Manual export; RPA solo con permiso explicito si fuera necesario. |
| Obralia / Nalanda construccion | XML legacy declarado. | Pagina historica indica XML para integracion ERP; sin contrato XML publico. | Integracion ERP/XML legacy. | Tratar como Nalanda legacy; pedir contrato moderno. |
| CoordinaPlus / Adding Plus | Integracion declarada; API no localizada. | Pagina producto declara integracion con ERP/control de accesos. | ERP, control de accesos, sistemas corporativos. | Solicitar documentacion privada. |
| Quioo / Quironprevencion | Integracion declarada; API no localizada. | Pagina producto declara integracion con ERP/control de accesos. | Control de accesos, ERP, SPA Quironprevencion, BIDI/estado. | Solicitar guia tecnica oficial. |

## Como queda guardado en el producto

La matriz anterior queda como referencia tecnica y no se expone en la navegacion diaria de la web local. La ruta `/platforms` es ahora el centro operativo de contextos plataforma + empresa + centro, no el catalogo tecnico.
El backend conserva estos campos en `/api/v1/platforms/catalog` bajo `technical_research`:

- `official_api_answer`
- `public_technical_docs_status`
- `documentation_url`
- `evidence_urls`
- `evidence_summary`
- `integration_surface`
- `next_action`
- `confidence`

Los metodos `official_api` y `authorized_rpa` siguen con `implemented=false` en todas las plataformas comerciales. Esto es intencional: una API declarada o una pagina comercial de integracion no bastan para implementar un conector real.

## Modelo tecnico de activacion futura

1. Alta de plataforma en `ExternalPlatform` con estado `researched_*`.
2. Metodo `manual_export` activo para preparar ZIP/checklist sin escritura externa.
3. Metodo `official_api` presente pero `implemented=false` hasta disponer de contrato oficial, credenciales y OpenAPI/WSDL/documentacion del proveedor.
4. Metodo `authorized_rpa` presente pero deshabilitado por defecto. Requiere autorizacion explicita, manifiesto, preflight y aprobacion humana.
5. Si Konvergia aplica, modelarlo como red independiente y no como permiso universal de escritura.

## Fuentes consultadas

- Dokify API: https://www.dokify.net/api
- Dokify CAE/Konvergia: https://www.dokify.net/en/cae
- Nalanda CAE: https://www.nalandaglobal.com/plataforma-cae/
- Nalanda status: https://status.nalandaglobal.com/
- Nalanda Konvergia: https://www.nalandaglobal.com/konvergia/
- Konvergia: https://konvergia.com/konvergia-la-unica-red-que-traslada-tus-documentos-a-otras-plataformas-de-manera-automatica/
- CTAIMA CAE: https://www.ctaima.com/plataforma-cae-ctaima/
- CTAIMA Developers: https://developers.ctaima.com/
- 6conecta CAE: https://www.6conecta.com/es/software-coordinacion-actividades-empresariales
- Metacontratas CAE: https://www.metacontratas.com/cae/
- Metacontratas guia 2026: https://www.metacontratas.com/como-elegir-la-mejor-plataforma-cae-en-2026-guia-completa/
- e-coordina integracion: https://www.e-coordina.es/integracion-de-la-cae-de-e-coordina/
- EcoGestor: https://www.ecogestor.com/
- EcoGestor CAE: https://www.ecogestor.com/ecogestor-cae/
- eGestiona: https://egestiona.com/
- UCAE: https://www.ucae.es/
- UCAE Konvergia: https://www.ucae.es/konvergia/
- SG Red: https://sgred.com/
- Sicondoc: https://www.sicondoc.com/?lang=en
- Validate CAE: https://validate.es/plataforma-cae/
- tdoc CAE: https://www.tdoc.es/plataforma-cae-tdoc/
- tdoc Access ayuda: https://help.tdoc.es/index.php/en/tdoc-access-manual/tdoc-access-web-access-en/
- Obralia/Nalanda constructoras: https://www.obralia.com/info_construc.html
- CoordinaPlus: https://www.coordinacae.com/home-2026/
- Quioo: https://quioo.quironprevencion.com/en/
