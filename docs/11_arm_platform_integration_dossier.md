# Dossier ARM de integracion de plataformas

Fecha: 2026-05-18.

## Alcance y limites

- Inventario basado en la hoja `ARM` del Excel local de requisitos.
- Captura con un unico intento de login normal por fila, sin bypass de captcha/MFA/controles anti-bot y sin escrituras externas.
- No se guardan contrasenas, cookies, tokens, cuerpos HTTP, HAR, capturas internas ni filas de datos personales.
- Los endpoints observados en navegador no son contrato API. Solo se consideran APIs cuando hay documentacion oficial o declaracion publica del proveedor.

## Resumen de capturas

- `initial_navigation_failed`: 2
- `login_form_not_found`: 9
- `login_likely_success`: 9
- `login_not_confirmed_password_form_still_present`: 8
- `stopped_control_detected_before_login`: 4

## Resumen por familia tecnica

| Familia | Resultado de capturas | Decision segura |
| --- | --- | --- |
| 6conecta | login_likely_success: 1 | Preparar mapeo/API solo si hay documentacion oficial; RPA autorizada posible solo con permiso formal y manifiesto. |
| CTAIMA CAE | stopped_control_detected_before_login: 3 | No automatizar; solicitar API/documentacion oficial o usar exportacion manual. |
| Dokify (URL Excel parece typo dokyfy.net) | initial_navigation_failed: 2 | Revisar URL/credenciales o solicitar mecanismo oficial; no implementar conector real todavia. |
| Folyo | login_not_confirmed_password_form_still_present: 1 | Revisar URL/credenciales o solicitar mecanismo oficial; no implementar conector real todavia. |
| Integra/Asem Web Services | login_form_not_found: 2 | Revisar URL/credenciales o solicitar mecanismo oficial; no implementar conector real todavia. |
| Koordinatu | login_form_not_found: 3 | Revisar URL/credenciales o solicitar mecanismo oficial; no implementar conector real todavia. |
| Metacontratas | stopped_control_detected_before_login: 1 | No automatizar; solicitar API/documentacion oficial o usar exportacion manual. |
| Nomio | login_likely_success: 1 | Preparar mapeo/API solo si hay documentacion oficial; RPA autorizada posible solo con permiso formal y manifiesto. |
| Quioo | login_form_not_found: 1 | Revisar URL/credenciales o solicitar mecanismo oficial; no implementar conector real todavia. |
| SGS Gestiona | login_not_confirmed_password_form_still_present: 1 | Revisar URL/credenciales o solicitar mecanismo oficial; no implementar conector real todavia. |
| SmartOSH | login_form_not_found: 2 | Revisar URL/credenciales o solicitar mecanismo oficial; no implementar conector real todavia. |
| Timenet/GPI | login_likely_success: 1 | Preparar mapeo/API solo si hay documentacion oficial; RPA autorizada posible solo con permiso formal y manifiesto. |
| UCAE | login_not_confirmed_password_form_still_present: 1 | Revisar URL/credenciales o solicitar mecanismo oficial; no implementar conector real todavia. |
| Validate | login_likely_success: 1 | Preparar mapeo/API solo si hay documentacion oficial; RPA autorizada posible solo con permiso formal y manifiesto. |
| Vitaly CAE | login_likely_success: 1 | Preparar mapeo/API solo si hay documentacion oficial; RPA autorizada posible solo con permiso formal y manifiesto. |
| e-coordina | login_likely_success: 4, login_not_confirmed_password_form_still_present: 2 | Preparar mapeo/API solo si hay documentacion oficial; RPA autorizada posible solo con permiso formal y manifiesto. |
| eGestiona | login_form_not_found: 1, login_not_confirmed_password_form_still_present: 1 | Revisar URL/credenciales o solicitar mecanismo oficial; no implementar conector real todavia. |
| ieDOCe | login_not_confirmed_password_form_still_present: 2 | Revisar URL/credenciales o solicitar mecanismo oficial; no implementar conector real todavia. |

## Detalle por fila

| Fila | Plataforma/cliente | Host | Estado login | Paginas | Artefacto |
| ---: | --- | --- | --- | ---: | --- |
| 2 | AGRISOLUTIONS | `agrisolutions.koordinatu.com` | `login_form_not_found` | 1 | `artifacts/platform-captures/arm-agrisolutions-20260518-091609/technical_capture.redacted.md` |
| 3 | ANTOLIN, LEAR | `www.dokyfy.net` | `initial_navigation_failed` | 1 | `artifacts/platform-captures/arm-antolin-lear-20260518-092302/technical_capture.redacted.md` |
| 4 | ARITEX | `v5.e-coordina.com` | `login_likely_success` | 2 | `artifacts/platform-captures/arm-aritex-20260518-091613/technical_capture.redacted.md` |
| 5 | ARKAL/NEMAK/FLORETTE | `secure.validate.network` | `login_likely_success` | 2 | `artifacts/platform-captures/arm-arkal-nemak-florette-20260518-091643/technical_capture.redacted.md` |
| 6 | ASPLA | `www.gestion.iedoce.com` | `login_not_confirmed_password_form_still_present` | 2 | `artifacts/platform-captures/arm-aspla-20260518-091701/technical_capture.redacted.md` |
| 7 | BELLOTA | `bellota.koordinatu.com` | `login_form_not_found` | 1 | `artifacts/platform-captures/arm-bellota-20260518-091706/technical_capture.redacted.md` |
| 8 | BSH Cartuja, Santander | `integra.asemwebservices.es` | `login_form_not_found` | 1 | `artifacts/platform-captures/arm-bsh-cartuja-santander-20260518-091709/technical_capture.redacted.md` |
| 9 | BSH Montañana | `sgs.sgs-gestiona.es` | `login_not_confirmed_password_form_still_present` | 2 | `artifacts/platform-captures/arm-bsh-monta-ana-20260518-091711/technical_capture.redacted.md` |
| 10 | CIE AUTOMOTIVE | `cieautomotive.koordinatu.com` | `login_form_not_found` | 1 | `artifacts/platform-captures/arm-cie-automotive-20260518-091728/technical_capture.redacted.md` |
| 11 | DETESA | `u5.ucae.es` | `login_not_confirmed_password_form_still_present` | 2 | `artifacts/platform-captures/arm-detesa-20260518-091758/technical_capture.redacted.md` |
| 12 | FAGOR + EDERTEK | `FAGOREDERLAN.EGESTIONA.ES` | `login_form_not_found` | 1 | `artifacts/platform-captures/arm-fagor-edertek-20260518-091803/technical_capture.redacted.md` |
| 13 | FAURECIA – FORVIA | `faurecia.egestiona.com` | `login_not_confirmed_password_form_still_present` | 2 | `artifacts/platform-captures/arm-faurecia-forvia-20260518-091805/technical_capture.redacted.md` |
| 14 | FLEXNGATE SABADELL / FLEXNAGATE PLÁSTICOS | `www.metacontratas.com` | `stopped_control_detected_before_login` | 1 | `artifacts/platform-captures/arm-flexngate-sabadell-flexnagate-pl-sticos-20260518-091823/technical_capture.redacted.md` |
| 15 | FOLYO | `seat.folyo.es` | `login_not_confirmed_password_form_still_present` | 2 | `artifacts/platform-captures/arm-folyo-20260518-091836/technical_capture.redacted.md` |
| 16 | FREUDENBERGNW-CLIENTE_E | `v5.e-coordina.com` | `login_likely_success` | 2 | `artifacts/platform-captures/arm-freudenbergnw-cliente_e-20260518-091854/technical_capture.redacted.md` |
| 17 | GESTAMP | `v5.e-coordina.com` | `login_likely_success` | 2 | `artifacts/platform-captures/arm-gestamp-20260518-091924/technical_capture.redacted.md` |
| 18 | GKN | `www.gestion.iedoce.com` | `login_not_confirmed_password_form_still_present` | 2 | `artifacts/platform-captures/arm-gkn-20260518-091954/technical_capture.redacted.md` |
| 19 | GRUPO CLIENTE_H, CLIENTE_E, CLIENTE_F, CLIENTE_G | `www.ctaimacae.net` | `stopped_control_detected_before_login` | 1 | `artifacts/platform-captures/arm-grupo-cliente_h-cliente_e-cliente_f-cliente_g-20260518-091959/technical_capture.redacted.md` |
| 20 | CLIENTE_D | `www.ctaimacae.net` | `stopped_control_detected_before_login` | 1 | `artifacts/platform-captures/arm-cliente_d-20260518-092007/technical_capture.redacted.md` |
| 21 | KAUTENIK, TEKNIA AMPUERO | `quioo.es` | `login_form_not_found` | 1 | `artifacts/platform-captures/arm-kautenik-teknia-ampuero-20260518-092010/technical_capture.redacted.md` |
| 22 | LONTANA GROUP | `integra.asemwebservices.es` | `login_form_not_found` | 1 | `artifacts/platform-captures/arm-lontana-group-20260518-092012/technical_capture.redacted.md` |
| 23 | MAXAM Y P&G (general servei) | `www.dokyfy.net` | `initial_navigation_failed` | 1 | `artifacts/platform-captures/arm-maxam-y-p-g-general-servei-20260518-092014/technical_capture.redacted.md` |
| 24 | Okin (Yaskawa) | `v5.e-coordina.com` | `login_not_confirmed_password_form_still_present` | 2 | `artifacts/platform-captures/arm-okin-yaskawa-20260518-092016/technical_capture.redacted.md` |
| 26 | SACOPA, FLUIDA, CEDEX, POLTANK | `v5.e-coordina.com` | `login_not_confirmed_password_form_still_present` | 2 | `artifacts/platform-captures/arm-sacopa-fluida-cedex-poltank-20260518-092045/technical_capture.redacted.md` |
| 28 | SEDA | `cae.vitaly.es` | `login_likely_success` | 2 | `artifacts/platform-captures/arm-seda-20260518-092104/technical_capture.redacted.md` |
| 29 | CLIENTE_A,CLIENTE_I,CLIENTE_B,CLIENTE_J,CLIENTE_C | `www.ctaimacae.net` | `stopped_control_detected_before_login` | 1 | `artifacts/platform-captures/arm-cliente_a-itp-cliente_b-seat-cliente_c-20260518-092116/technical_capture.redacted.md` |
| 30 | TENNECO | `v5.e-coordina.com` | `login_likely_success` | 2 | `artifacts/platform-captures/arm-tenneco-20260518-092120/technical_capture.redacted.md` |
| 31 | TI AUTOMOTIVE | `tiautomotive.smartosh.com` | `login_form_not_found` | 1 | `artifacts/platform-captures/arm-ti-automotive-20260518-092150/technical_capture.redacted.md` |
| 32 | TIMENET | `timenet.gpisoftware.com` | `login_likely_success` | 4 | `artifacts/platform-captures/arm-timenet-20260518-092153/technical_capture.redacted.md` |
| 33 | VELARTIA IGORRE / CONGELADOS DENAVARRA | `www.6conecta.com` | `login_likely_success` | 6 | `artifacts/platform-captures/arm-velartia-igorre-congelados-denavarra-20260518-092159/technical_capture.redacted.md` |
| 34 | NOMIO | `app.nomio.io` | `login_likely_success` | 6 | `artifacts/platform-captures/arm-nomio-20260518-092227/technical_capture.redacted.md` |
| 35 | GESTAMP ABRERA | `gestamp-abrera.smartosh.com` | `login_form_not_found` | 1 | `artifacts/platform-captures/arm-gestamp-abrera-20260518-092237/technical_capture.redacted.md` |

Nota 2026-05-19: se repitio la captura tecnica de la fila ARM 29 para CTAIMA/CLIENTE_A. El resultado volvio a ser `stopped_control_detected_before_login` con captcha detectado antes de localizar campos de usuario/password. Artefacto: `artifacts/platform-captures/cliente_a-itp-cliente_b-seat-cliente_c-20260519-134307/technical_capture.redacted.md`.

## APIs oficiales/localizadas

| Plataforma | Estado API | Fuente |
| --- | --- | --- |
| Dokify | API oficial declarada; pagina oficial indica entidades Checkin, Employee, Group, Client, Machine, Company, Document y User; requiere acceso/licencia a la documentacion tecnica. | https://www.dokify.net/api |
| CTAIMA | Portal oficial de desarrollador con catalogo de APIs, documentacion tecnica, consola y productos; detalle requiere cuenta. | https://developers.ctaima.com/apis |
| e-coordina | Servicio web declarado, URL con salidas CSV/JSON/XML, creacion de trabajadores/empresas/proyectos/trabajos y sincronizaciones; requiere contrato tecnico. | https://www.e-coordina.es/integracion-de-la-cae-de-e-coordina/ |
| Validate | Servicio Web declarado para consultar datos y situacion de acceso de trabajadores desde control de accesos; requiere especificacion. | https://validate.es/plataforma-cae/ |
| 6conecta | API Control Accesos e integraciones declaradas en pagina CAE; no hay especificacion publica completa. | https://www.6conecta.com/es/software-coordinacion-actividades-empresariales |
| eGestiona | eData Sync/eAccess Sync declara servicios web API y SFTP para acreditaciones, documentos y datos de trabajadores/equipos/empresas. | https://egestiona.com/edata-sync/ |
| UCAE | Pagina de control de accesos declara integracion con APIs para consultar trabajadores y estado documental de empresa, empleados y maquinaria. | https://www.ucae.es/control-de-accesos/ |
| Timenet/GPI | Modulo avanzado declara API de conexion e importacion/exportacion a Excel/CSV/JSON; requiere kit/documentacion de GPI. | https://www.timenetapp.com/ca/moduls/modul-avancat |
| Quioo | Declara integracion con sistemas de control de accesos y SPA, pero no publica especificacion API. | https://quioo.quironprevencion.com/ |
| Nomio | No se localizo API publica oficial; producto web de nominas con tutoriales y datos laborales sensibles. | https://nomio.io/ |
| Vitaly CAE | No se localizo API publica oficial; pagina CAE describe servicio/gestion. | https://vitaly.es/area/cae/ |
| SmartOSH | Declara integracion de sistemas de gestion, sin API publica localizada para SmartOSH CAE. | https://www.smartosh.com/ |
| ieDOCe | No se localizo API publica oficial; pagina describe plataforma web CAE y validaciones. | https://iedoce.com/ |
| Metacontratas | No se localizo API publica oficial; pagina describe migracion/implantacion y plataforma CAE. | https://www.metacontratas.com/cae/ |

## Contrato minimo de integracion futura

Toda integracion real debe aportar antes de implementar: OpenAPI/WSDL/guia oficial, base URL autorizada, sandbox, credenciales tecnicas, limites de uso, contrato/DPA, operaciones permitidas, mapeo documental, estados externos, politica de aprobacion manual y auditoria antes/despues.

## Proximo paso tecnico seguro

- Activar solo `manual_export` para todas las familias sin contrato API.
- Crear conectores API concretos solamente para familias con documentacion oficial entregada por proveedor: primero `ecoordina`, `dokify`, `ctaima`, `validate`, `egestiona`, `ucae`, `timenet` o `6conecta` segun contrato disponible.
- Mantener cualquier RPA comercial deshabilitada por defecto y sujeta a manifiesto autorizado, `dry_run`, aprobacion humana y auditoria.
