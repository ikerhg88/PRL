# 00 — Dossier de investigación: Konvergia

Fecha: 2026-05-16.
Alcance: información pública disponible en Konvergia, Nalanda, Metacontratas y UCAE.

## 1. Identificación

- Nombre comercial: Konvergia.
- Razón social publicada: KONVERGIA PLATAFORMAS AGRUPADAS A.I.E.
- CIF publicado: V88409313.
- Dirección publicada: C/Aguacate, nº 41, Portal B4, 28054 Madrid.
- Email de contacto de privacidad publicado: hola@konvergia.com.
- DPO publicado: dpo@konvergia.com.

## 2. Estado actual del servicio

Las fuentes públicas indican que Konvergia se encuentra en cierre:

- La página principal muestra un aviso de cierre del servicio y nuevos registros deshabilitados.
- El hub público indexado indica que el sistema cesará su actividad, incluida la transferencia de documentos, el 19 de junio de 2026.

Implicación para IKER: Konvergia debe estudiarse como referencia funcional, no como dependencia operativa. El producto IKER debe replicar el patrón de valor, no depender de Konvergia.

## 3. Problema que resolvía

Konvergia nace por la proliferación de plataformas CAE. Contratas, subcontratas y empresas de servicios acababan subiendo la misma documentación de PRL/CAE en múltiples portales diferentes. El objetivo era reducir tareas repetitivas, errores y coste administrativo.

Puntos funcionales clave:

- Subida única de un documento.
- Distribución automática a varias plataformas CAE asociadas.
- Lenguaje común/catálogo compartido de tipos documentales.
- Panel centralizado de transferencias.
- Control de estado por plataforma.
- Validación final hecha por cada plataforma receptora según sus propios criterios.

## 4. Socios/plataformas mencionadas públicamente

Las fuentes varían según año y página. Socios/plataformas mencionadas:

- UCAE.
- Dokify.
- Metacontratas.
- EcoGestor.
- Nalanda.
- Tesicnor.
- Construred.
- 6Conecta.
- SGred.

Observación: en 2019 se habla de ocho plataformas; en artículos de 2021 se habla de siete; en páginas posteriores aparece Nalanda integrada y se listan nueve marcas. Para IKER conviene modelar las plataformas como catálogo dinámico, no como lista fija.

## 5. Línea temporal pública

- Principios de 2018: reuniones iniciales y viabilidad técnica de comunicación entre plataformas CAE.
- 2019: constitución o consolidación de Konvergia como asociación/AIE de plataformas agrupadas.
- Mayo de 2021: comunicación pública de la beta operativa.
- Junio de 2021: más de 200 empresas adheridas a la beta y más de 10.000 documentos transferidos automáticamente.
- Enero de 2022: explicación pública del panel de control y del catálogo común con más de 300 tipos documentales.
- Mayo de 2024: Nalanda anuncia su integración en Konvergia.
- 2026: aviso público de cierre del servicio y registros deshabilitados; el hub indexado indica cese de transferencias el 19 de junio de 2026.

## 6. Modelo funcional de Konvergia

### 6.1. Flujo básico

1. El usuario entra en una de las plataformas asociadas.
2. Sube un documento como lo hacía habitualmente.
3. La plataforma origen identifica el tipo documental mediante un código común.
4. El sistema detecta en qué otras plataformas asociadas falta ese documento o está próximo a caducar.
5. El documento se remite a esas plataformas destino.
6. Cada plataforma destino valida el documento según sus criterios propios.
7. El usuario puede consultar el estado desde Konvergia o desde cada plataforma.

### 6.2. Activación en Nalanda

La documentación pública de Nalanda describe esta activación:

- Entrar en Nalanda.
- Ir a “Administrador”.
- En “Mi Empresa / Centro de Negocio”, seleccionar “Konvergia”.
- Registrarse una única vez en Konvergia.
- Seleccionar modo de envío/recepción.

### 6.3. Modos de envío/recepción descritos por Nalanda

- Recibir y enviar: los documentos subidos en Nalanda se envían a plataformas asociadas, y los subidos en otras plataformas se reciben en Nalanda.
- Recibir documentos: Nalanda recibe documentos subidos en otras plataformas asociadas.
- Enviar documentos: Nalanda envía a plataformas asociadas documentos subidos en Nalanda.

Para IKER, estos modos deben convertirse en una configuración por plataforma, tenant y tipo documental.

## 7. Panel de control de Konvergia

Konvergia describe un panel para ver transferencias documentales. Campos funcionales publicados:

- Fecha y hora de carga/transferencia.
- Empresa o trabajador asociado.
- Plataforma de origen.
- Plataforma o plataformas destino.
- Tipo documental.
- Fichero cargado.
- Código de tipo documental.

Para IKER, este panel debe implementarse como una tabla de auditoría de transferencias con filtros por empresa, trabajador, plataforma, documento, estado y rango temporal.

## 8. Catálogo común de documentos

Konvergia declara un compendio de más de 300 tipos documentales, cada uno con código propio. La finalidad es que las plataformas “hablen” el mismo lenguaje documental.

Limitación publicada: el catálogo común no cubre documentos particulares de empresas principales, por ejemplo formularios propios descargables que una contrata debe cumplimentar y firmar. IKER debe contemplar dos capas:

1. Catálogo documental común.
2. Requisitos particulares por cliente/centro/actividad/plataforma.

## 9. Tipos documentales identificados públicamente

### 9.1. Documentos de empresa

Normalizados para IKER:

- Escrituras de constitución.
- CIF/NIF de empresa.
- Mutua de accidentes de trabajo.
- Póliza de responsabilidad civil.
- Recibo de responsabilidad civil.
- Certificado de estar al corriente con AEAT.
- Póliza de seguro de convenio.
- Recibo de seguro de convenio.
- REA.
- Certificado de estar al corriente con Seguridad Social.
- RLC/TC1.
- RNT/TC2 cuando aplique.
- ITA.
- Recibo del servicio de prevención.
- Sistema de gestión de calidad.
- Sistema de gestión medioambiental.
- Evaluación de riesgos laborales.
- IAE.
- Certificado de cobro de salarios, citado como ejemplo de requisito común en Konvergia.

### 9.2. Documentación de trabajadores

Normalizados para IKER:

- IDC o cuota de autónomo.
- Autorización de uso de máquinas/equipos.
- Aptitud médica o documento de renuncia.
- DNI/NIE/pasaporte/permiso de trabajo y residencia.
- Entrega de EPIs.
- Curso básico de prevención.
- Formación de puesto de trabajo.
- Información de riesgos laborales entregada al trabajador.

## 10. Reglas de versiones y conflictos

Nalanda indica que, si se carga el mismo documento en varias plataformas con distintas versiones, Konvergia conserva la última versión subida, respetando la configuración de envío y recepción.

Para IKER:

- Cada documento debe tener versiones inmutables.
- Debe existir política de “versión ganadora”.
- La política por defecto puede ser `latest_uploaded_wins`, pero debe permitir excepciones.
- Debe registrarse la fuente de la versión: manual, API, RPA, importación, OCR, plataforma externa.

## 11. Validación

Konvergia no sustituye la validación de cada plataforma. Cada plataforma valida el documento con sus criterios propios.

Para IKER:

- El estado interno del documento no debe confundirse con el estado externo.
- Un documento puede estar “válido internamente” pero “rechazado en plataforma X”.
- Debe existir una tabla `external_validation_status` por plataforma, requisito y versión documental.

## 12. Beneficios declarados

- Ahorro de tiempo.
- Menos esfuerzo administrativo.
- Menos costes operativos.
- Eficiencia y eficacia.
- Buenas prácticas entre plataformas.
- Mayor centralización y capacidad de detectar incumplimientos.
- Mejor coordinación de contratistas y subcontratistas.

## 13. Limitaciones detectadas

- No hay API pública documentada localizada en fuentes abiertas.
- El servicio se encuentra en cierre.
- Los nuevos registros están deshabilitados.
- Los formularios particulares de clientes no forman parte del catálogo común.
- La validación sigue dependiendo de cada plataforma.
- El acceso al hub requiere usuario/contraseña.
- La automatización real entre plataformas se basaba en acuerdos entre socios, no en scraping externo.

## 14. Implicaciones para el diseño de IKER

IKER debería adoptar estos patrones:

1. Catálogo común de tipos documentales con códigos internos.
2. Mapeos por plataforma y cliente.
3. Versionado documental fuerte.
4. Panel de transferencias por origen/destino.
5. Modos `send`, `receive`, `send_receive`, `disabled`.
6. Estado documental multidimensional: interno, por plataforma, por cliente, por centro, por trabajador.
7. Requisitos particulares configurables.
8. Conectores independientes y sustituibles.
9. Fallback de exportación asistida.
10. Automatización de navegador únicamente en contextos autorizados y con trazabilidad.

## 15. Preguntas abiertas para investigación comercial/técnica

- ¿Qué contratos o permisos tenían las plataformas socias para intercambiar documentos?
- ¿Existió una API común privada entre plataformas?
- ¿Qué formato tenía el código documental común?
- ¿Cómo se gestionaban rechazos y observaciones?
- ¿Cómo se gestionaba la protección de datos de documentos de trabajadores?
- ¿Qué coste tenía la tarifa propia de Konvergia tras la beta?
- ¿Qué impacto tiene el cierre del servicio para clientes activos?
- ¿Qué socios mantendrán alternativas propias o integraciones directas?
