from __future__ import annotations

from pydantic import BaseModel, Field


class PlatformConnectionMethodItem(BaseModel):
    method_key: str
    connector_type: str
    connector_key: str | None
    status: str
    implemented: bool
    dry_run_supported: bool = True
    manual_approval_required: bool = True
    notes: str


class PlatformTechnicalResearch(BaseModel):
    researched_at: str = "2026-05-17"
    official_api_answer: str = "not_applicable"
    public_technical_docs_status: str = "not_applicable"
    documentation_url: str | None = None
    documentation_label: str | None = None
    evidence_urls: list[str] = Field(default_factory=list)
    evidence_summary: str = "Sin documentacion tecnica externa aplicable."
    integration_surface: list[str] = Field(default_factory=list)
    next_action: str = "Mantener en catalogo hasta que exista necesidad de integracion."
    confidence: str = "internal"


class PlatformCatalogItem(BaseModel):
    platform_key: str
    name: str
    status: str
    is_commercial: bool
    notes: str
    methods: list[PlatformConnectionMethodItem]
    technical_research: PlatformTechnicalResearch = Field(default_factory=PlatformTechnicalResearch)


def _research(
    *,
    official_api_answer: str,
    public_technical_docs_status: str,
    documentation_url: str | None,
    documentation_label: str | None,
    evidence_urls: list[str],
    evidence_summary: str,
    integration_surface: list[str],
    next_action: str,
    confidence: str = "high_public_official",
) -> PlatformTechnicalResearch:
    return PlatformTechnicalResearch(
        official_api_answer=official_api_answer,
        public_technical_docs_status=public_technical_docs_status,
        documentation_url=documentation_url,
        documentation_label=documentation_label,
        evidence_urls=evidence_urls,
        evidence_summary=evidence_summary,
        integration_surface=integration_surface,
        next_action=next_action,
        confidence=confidence,
    )


TECHNICAL_RESEARCH: dict[str, PlatformTechnicalResearch] = {
    "mock_cae": _research(
        official_api_answer="not_applicable_local_mock",
        public_technical_docs_status="local_contract_in_code",
        documentation_url=None,
        documentation_label="Contrato local de prueba",
        evidence_urls=[],
        evidence_summary="Plataforma mock local para validar contratos internos sin terceros.",
        integration_surface=["demo_simulation", "manual_export"],
        next_action="Usarla como banco de pruebas antes de activar cualquier integracion comercial.",
        confidence="verified_internal",
    ),
    "dokify": _research(
        official_api_answer="yes_public_api_product_gated_details",
        public_technical_docs_status="public_api_page_claims_references_examples_search",
        documentation_url="https://www.dokify.net/api",
        documentation_label="Pagina oficial API dokify",
        evidence_urls=["https://www.dokify.net/api"],
        evidence_summary=(
            "Dokify publica una pagina oficial de API y afirma que esta documentada con referencias, "
            "ejemplos y buscador. Cubre Checkin, Employee, Group, Client, Machine, Company, Document y User. "
            "No se ha localizado OpenAPI/base URL publica sin alta."
        ),
        integration_surface=["checkin", "employee", "group", "client", "machine", "company", "document", "user"],
        next_action="Solicitar acceso a documentacion tecnica, sandbox, limites y contrato antes de crear connector_api_dokify.",
    ),
    "nalanda": _research(
        official_api_answer="yes_api_component_visible_private_docs",
        public_technical_docs_status="public_product_page_and_status_api_component",
        documentation_url="https://status.nalandaglobal.com/",
        documentation_label="Status publico Nalanda API",
        evidence_urls=[
            "https://www.nalandaglobal.com/plataforma-cae/",
            "https://status.nalandaglobal.com/",
            "https://www.nalandaglobal.com/konvergia/",
        ],
        evidence_summary=(
            "Nalanda declara integracion informatica con ERP y su status publico separa CAE Construction (API). "
            "No se ha localizado contrato OpenAPI/WSDL publico."
        ),
        integration_surface=["cae_construction_api", "erp_integration", "konvergia_network"],
        next_action="Pedir documentacion API de CAE Construction, credenciales sandbox y condiciones de uso.",
    ),
    "konvergia": _research(
        official_api_answer="no_public_api_found_network_service",
        public_technical_docs_status="public_functional_network_docs_only",
        documentation_url="https://konvergia.com/",
        documentation_label="Web oficial Konvergia",
        evidence_urls=[
            "https://konvergia.com/",
            "https://www.nalandaglobal.com/konvergia/",
            "https://konvergia.com/aviso-legal/",
        ],
        evidence_summary=(
            "Konvergia describe una red de intercambio documental entre plataformas y muestra aviso de cierre de servicio. "
            "No hay documentacion API publica localizada."
        ),
        integration_surface=["document_network", "send_receive_modes", "status_panel"],
        next_action="Mantener como referencia funcional; no depender de Konvergia como integracion operativa.",
    ),
    "ctaima_cae": _research(
        official_api_answer="yes_developer_portal_public_gated_api_details",
        public_technical_docs_status="public_developer_portal_azure_api_management",
        documentation_url="https://developers.ctaima.com/apis",
        documentation_label="Portal desarrollador CTAIMA APIs",
        evidence_urls=[
            "https://developers.ctaima.com/",
            "https://developers.ctaima.com/apis",
            "https://developers.ctaima.com/products",
        ],
        evidence_summary=(
            "CTAIMA publica portal de desarrollador con catalogo de APIs, documentacion tecnica, consola de prueba "
            "y productos con limites de peticiones sobre Azure API Management. El detalle requiere cuenta."
        ),
        integration_surface=["ctaima_cae_net_api", "developer_products", "api_console"],
        next_action="Crear cuenta de desarrollador/contrato y documentar APIs concretas antes de implementar.",
    ),
    "sixconecta": _research(
        official_api_answer="yes_api_declared_private_docs",
        public_technical_docs_status="public_product_page_api_mentions",
        documentation_url="https://www.6conecta.com/es/software-coordinacion-actividades-empresariales",
        documentation_label="6conecta CAE e integraciones",
        evidence_urls=["https://www.6conecta.com/es/software-coordinacion-actividades-empresariales"],
        evidence_summary=(
            "6conecta declara integracion con control de accesos, compras, usuarios/autenticacion y BI, "
            "incluyendo modulo API Control Accesos. No se ha localizado especificacion API publica."
        ),
        integration_surface=["access_control_api", "purchasing", "user_authentication", "business_intelligence"],
        next_action="Solicitar referencia privada de API, alcance de endpoints y entorno de prueba.",
    ),
    "metacontratas": _research(
        official_api_answer="no_public_api_found",
        public_technical_docs_status="public_help_center_user_manuals_only",
        documentation_url="https://ayuda.metacontratas.com/en/articles/8263109-upload-documentation-to-several-main-companies",
        documentation_label="Ayuda Metacontratas subida multicliente",
        evidence_urls=[
            "https://www.metacontratas.com/cae/",
            "https://ayuda.metacontratas.com/en/articles/8263109-upload-documentation-to-several-main-companies",
        ],
        evidence_summary=(
            "Se localiza documentacion funcional y de ayuda para usuarios, incluido panel de acceso unificado y subida "
            "a varias empresas principales. No aparece API oficial publica."
        ),
        integration_surface=["user_help_center", "unified_access_panel", "manual_document_upload"],
        next_action="Usar manual_export; pedir API o mecanismo oficial si un cliente lo requiere.",
    ),
    "ecoordina": _research(
        official_api_answer="yes_service_web_declared_public_integration_page",
        public_technical_docs_status="public_integration_page_no_contract_spec",
        documentation_url="https://www.e-coordina.es/integracion-de-la-cae-de-e-coordina/",
        documentation_label="Integracion e-coordina",
        evidence_urls=["https://www.e-coordina.es/integracion-de-la-cae-de-e-coordina/"],
        evidence_summary=(
            "e-coordina describe servicio web, acceso por URL con salidas CSV/JSON/XML, acciones como alta de "
            "trabajadores/empresas/proyectos/trabajos y sincronizaciones hacia servicios externos."
        ),
        integration_surface=["service_web", "url_csv_json_xml", "create_workers_companies_projects_jobs", "external_sync"],
        next_action="Solicitar WSDL/OpenAPI, autenticacion, limites y sandbox; posible prioridad alta para primer API real.",
    ),
    "ecogestor": _research(
        official_api_answer="yes_web_service_declared_private_docs",
        public_technical_docs_status="public_product_page_web_service",
        documentation_url="https://www.ecogestor.com/ecogestor-cae/",
        documentation_label="EcoGestor CAE Web Service",
        evidence_urls=["https://www.ecogestor.com/ecogestor-cae/"],
        evidence_summary=(
            "EcoGestor CAE declara Web Service para integracion con plataformas de acceso al centro de trabajo, "
            "como barreras y tornos. No publica contrato tecnico abierto."
        ),
        integration_surface=["access_control_web_service", "barriers", "turnstiles"],
        next_action="Solicitar documentacion web service y condiciones de integracion por cliente.",
    ),
    "egestiona": _research(
        official_api_answer="yes_api_declared_private_docs",
        public_technical_docs_status="public_api_product_page_no_endpoint_spec",
        documentation_url="https://egestiona.com/edata-sync/",
        documentation_label="eGestiona eData Sync",
        evidence_urls=["https://egestiona.com/edata-sync/", "https://egestiona.com/api-edata-sync/"],
        evidence_summary=(
            "eGestiona declara eData Sync/API eAccess Sync para obtener acreditaciones de trabajadores, equipos y empresas, "
            "documentos vinculados, canales SSL y alternativa SFTP. No publica endpoints."
        ),
        integration_surface=["edata_sync", "eaccess_sync", "ssl_web_services", "sftp_file_exchange"],
        next_action="Solicitar contrato API eData/eAccess Sync, campos, autenticacion y ejemplo de payload.",
    ),
    "ucae": _research(
        official_api_answer="no_public_api_found",
        public_technical_docs_status="public_product_pages_only",
        documentation_url="https://www.ucae.es/",
        documentation_label="UCAE plataforma CAE",
        evidence_urls=[
            "https://www.ucae.es/",
            "https://www.ucae.es/konvergia/",
            "https://www.ucae.es/cargamos-la-documentacion-cae-en-otras-plataformas-por-ti/",
        ],
        evidence_summary=(
            "UCAE publica gestion CAE, archivo documental, control de accesos y servicio de carga en otras plataformas. "
            "No se ha localizado API tecnica publica."
        ),
        integration_surface=["document_archive", "third_party_platform_upload_service", "access_control", "konvergia"],
        next_action="Usar exportacion asistida; pedir mecanismo oficial si se contrata servicio tecnico.",
    ),
    "sgred": _research(
        official_api_answer="no_public_api_found",
        public_technical_docs_status="public_product_and_konvergia_docs_only",
        documentation_url="https://sgred.com/2019/07/02/conexion-konvergia/",
        documentation_label="SG Red conexion Konvergia",
        evidence_urls=["https://sgred.com/", "https://sgred.com/2019/07/02/conexion-konvergia/"],
        evidence_summary=(
            "SG Red publica gestion documental, carga de ficheros y adhesion a Konvergia para intercambio automatico. "
            "No se ha localizado API oficial publica."
        ),
        integration_surface=["document_management", "file_upload", "konvergia_network"],
        next_action="Mantener en manual_export hasta obtener documentacion privada o autorizacion.",
    ),
    "sicondoc_construred": _research(
        official_api_answer="no_public_api_found",
        public_technical_docs_status="public_product_blog_only",
        documentation_url="https://www.sicondoc.com/lanzamiento-de-sicondoc-plataforma-de-gestion-documental/",
        documentation_label="Sicondoc lanzamiento plataforma",
        evidence_urls=["https://www.sicondoc.com/lanzamiento-de-sicondoc-plataforma-de-gestion-documental/"],
        evidence_summary=(
            "Sicondoc se describe como plataforma de gestion documental, estado documental, control de accesos y servicio "
            "integrado con ERP Sicon. No se ha localizado API publica."
        ),
        integration_surface=["document_management", "access_control", "sicon_erp_context"],
        next_action="Usar como catalogo de referencia; solicitar documentacion si aparece cliente Sicondoc.",
    ),
    "validate": _research(
        official_api_answer="yes_web_service_declared_private_docs",
        public_technical_docs_status="public_product_page_web_service",
        documentation_url="https://validate.es/plataforma-cae/",
        documentation_label="Validate CAE Web Service",
        evidence_urls=["https://validate.es/plataforma-cae/", "https://validate.es/home/"],
        evidence_summary=(
            "Validate declara Web Service para consulta online de datos y situacion de acceso de cada trabajador "
            "desde sistemas de control de accesos. No publica endpoints."
        ),
        integration_surface=["access_status_web_service", "worker_access_query", "access_control_systems"],
        next_action="Solicitar especificacion del Web Service y modelo de autenticacion antes de cualquier conector.",
    ),
    "tdoc": _research(
        official_api_answer="no_public_api_found",
        public_technical_docs_status="public_help_center_user_manuals_only",
        documentation_url="https://help.tdoc.es/index.php/en/tdoc-access-manual/tdoc-access-web-access-en/",
        documentation_label="Manual tdoc Access web",
        evidence_urls=[
            "https://www.tdoc.es/plataforma-cae-tdoc/",
            "https://help.tdoc.es/index.php/en/tdoc-access-manual/tdoc-access-web-access-en/",
        ],
        evidence_summary=(
            "tdoc publica producto CAE y manuales de tdoc Access para consultar accesos/estado documental y exportar. "
            "No se ha localizado API publica oficial."
        ),
        integration_surface=["tdoc_access_web", "access_status_view", "excel_export"],
        next_action="Mantener manual_export; pedir API privada si se necesita automatizacion autorizada.",
    ),
    "obralia": _research(
        official_api_answer="xml_integration_legacy_declared",
        public_technical_docs_status="public_legacy_xml_integration_claim",
        documentation_url="https://www.obralia.com/info_construc.html",
        documentation_label="Obralia/Nalanda XML ERP",
        evidence_urls=["https://www.obralia.com/info_construc.html"],
        evidence_summary=(
            "La pagina historica de Obralia/Nalanda declara integracion con ERP y XML desarrollado para integraciones. "
            "No publica contrato XML ni API moderna."
        ),
        integration_surface=["legacy_xml", "erp_integration"],
        next_action="Tratar como referencia legacy; pedir contrato moderno Nalanda antes de implementar.",
    ),
    "koordinatu": _research(
        official_api_answer="no_public_api_found",
        public_technical_docs_status="no_public_technical_docs_found",
        documentation_url=None,
        documentation_label="Captura ARM autorizada de subdominios Koordinatu",
        evidence_urls=[],
        evidence_summary=(
            "El Excel ARM contiene varios subdominios Koordinatu. La captura read-only no localizo formulario "
            "de login estandar en la URL base y no se ha localizado documentacion API publica."
        ),
        integration_surface=["cae_portal_observed", "manual_export_candidate"],
        next_action="Solicitar documentacion oficial o URL de integracion al proveedor antes de crear conector.",
        confidence="internal_capture_plus_public_search",
    ),
    "iedoce": _research(
        official_api_answer="no_public_api_found",
        public_technical_docs_status="public_product_page_only",
        documentation_url="https://iedoce.com/",
        documentation_label="ieDOCe plataforma CAE",
        evidence_urls=["https://iedoce.com/", "https://iedoce.com/que-es-iedoce/"],
        evidence_summary=(
            "ieDOCe publica plataforma web CAE, gestion de empresas/centros/proyectos, requisitos, personas, "
            "equipos, vehiculos, accesos e historicos. No se ha localizado API publica."
        ),
        integration_surface=["cae_web_platform", "document_validation", "access_tracking"],
        next_action="Mantener manual_export y solicitar API/contrato tecnico si ARM requiere integracion.",
    ),
    "asemwebservices_integra": _research(
        official_api_answer="no_public_api_found",
        public_technical_docs_status="no_public_technical_docs_found",
        documentation_url=None,
        documentation_label="Integra/Asem Web Services observado en ARM",
        evidence_urls=[],
        evidence_summary=(
            "El Excel ARM referencia integra.asemwebservices.es. La captura no localizo login automatizable "
            "en la URL inicial y no se ha localizado especificacion API publica."
        ),
        integration_surface=["observed_login_portal", "manual_export_candidate"],
        next_action="Confirmar proveedor real y pedir documentacion oficial antes de cualquier conector.",
        confidence="internal_capture",
    ),
    "sgs_gestiona": _research(
        official_api_answer="no_public_api_found",
        public_technical_docs_status="no_public_technical_docs_found",
        documentation_url=None,
        documentation_label="SGS Gestiona observado en ARM",
        evidence_urls=[],
        evidence_summary=(
            "El Excel ARM referencia sgs.sgs-gestiona.es. La captura no confirmo login correcto y no se ha "
            "localizado referencia API publica especifica."
        ),
        integration_surface=["observed_login_portal", "manual_export_candidate"],
        next_action="Validar alcance contractual con SGS/gestiona antes de planificar integracion.",
        confidence="internal_capture",
    ),
    "folyo": _research(
        official_api_answer="no_public_api_found",
        public_technical_docs_status="no_public_technical_docs_found",
        documentation_url=None,
        documentation_label="Folyo observado en ARM",
        evidence_urls=[],
        evidence_summary=(
            "El Excel ARM referencia seat.folyo.es. La captura no confirmo login correcto y no se ha localizado "
            "documentacion API publica."
        ),
        integration_surface=["observed_login_portal", "manual_export_candidate"],
        next_action="Solicitar documentacion tecnica o mecanismo de exportacion/importacion oficial.",
        confidence="internal_capture",
    ),
    "vitaly_cae": _research(
        official_api_answer="no_public_api_found",
        public_technical_docs_status="public_product_page_only",
        documentation_url="https://vitaly.es/area/cae/",
        documentation_label="Vitaly CAE",
        evidence_urls=["https://vitaly.es/area/cae/"],
        evidence_summary=(
            "Vitaly publica servicio CAE y la captura ARM confirmo login normal en cae.vitaly.es. No se ha "
            "localizado API publica."
        ),
        integration_surface=["cae_service", "observed_client_selection"],
        next_action="Usar manual_export salvo que Vitaly entregue API/sandbox o guia tecnica autorizada.",
    ),
    "smartosh": _research(
        official_api_answer="integration_declared_no_public_api_spec",
        public_technical_docs_status="public_product_pages_integration_claim",
        documentation_url="https://www.smartosh.com/",
        documentation_label="SmartOSH",
        evidence_urls=[
            "https://www.smartosh.com/",
            "https://www.smartosh.com/validacion-documental-cae-mediante-ia/",
        ],
        evidence_summary=(
            "SmartOSH publica gestion avanzada de SST/CAE e integracion de sistemas de gestion. No se ha "
            "localizado especificacion API publica."
        ),
        integration_surface=["system_integration_claim", "cae_document_validation"],
        next_action="Solicitar API/SDK oficial o contrato de integracion antes de implementar.",
    ),
    "timenet": _research(
        official_api_answer="yes_api_declared_private_docs",
        public_technical_docs_status="public_integration_pages_no_endpoint_spec",
        documentation_url="https://www.timenetapp.com/ca/moduls/modul-avancat",
        documentation_label="Timenet modul avancat API",
        evidence_urls=[
            "https://www.timenetapp.com/ca/moduls/modul-avancat",
            "https://www.gpisoftware.com/es/nuestros-distribuidores/desarrolladores-externos",
        ],
        evidence_summary=(
            "Timenet/GPI declara API de conexion, kit de desarrollo e importacion/exportacion en Excel, CSV y JSON. "
            "No publica endpoints ni contrato completo."
        ),
        integration_surface=["connection_api", "custom_import_export", "excel_csv_json"],
        next_action="Solicitar kit de desarrollo GPI, autenticacion, limites y entorno de prueba.",
    ),
    "nomio": _research(
        official_api_answer="no_public_api_found",
        public_technical_docs_status="public_product_and_tutorial_pages_only",
        documentation_url="https://nomio.io/",
        documentation_label="Nomio programa nominas",
        evidence_urls=["https://nomio.io/"],
        evidence_summary=(
            "Nomio publica producto web de nominas y tutoriales funcionales. La captura ARM confirmo login normal, "
            "pero no se ha localizado API publica y trata datos laborales sensibles."
        ),
        integration_surface=["payroll_web_platform", "workers", "companies", "periods", "incidents"],
        next_action="No crear conector sin contrato/API oficial y evaluacion RGPD reforzada.",
    ),
    "coordinaplus": _research(
        official_api_answer="integration_declared_no_public_api_spec",
        public_technical_docs_status="public_product_page_integration_claim",
        documentation_url="https://www.coordinacae.com/",
        documentation_label="CoordinaPlus integraciones",
        evidence_urls=["https://www.coordinacae.com/"],
        evidence_summary=(
            "CoordinaPlus declara integracion CAE con ERP, control de accesos y otros sistemas corporativos. "
            "No se ha localizado especificacion API publica."
        ),
        integration_surface=["erp_integration", "access_control_integration", "corporate_systems"],
        next_action="Pedir documentacion privada; mantener solo manual_export en la version actual.",
    ),
    "quioo": _research(
        official_api_answer="integration_declared_no_public_api_spec",
        public_technical_docs_status="public_product_page_integration_claim",
        documentation_url="https://quioo.quironprevencion.com/",
        documentation_label="Quioo CAE integraciones",
        evidence_urls=[
            "https://quioo.quironprevencion.com/",
            "https://quioo.quironprevencion.com/en/plataforma-cae/",
        ],
        evidence_summary=(
            "Quioo declara integracion con sistemas de control de accesos, ERP y otras soluciones empresariales, "
            "pero no publica especificacion API."
        ),
        integration_surface=["access_control_integration", "erp_integration", "spa_integration", "bidi_status"],
        next_action="Solicitar API o guia tecnica oficial a Quironprevencion antes de cualquier conector.",
    ),
    "sarenet": _research(
        official_api_answer="no_cae_api_confirmed",
        public_technical_docs_status="internal_arm_contract_bundle_only",
        documentation_url=None,
        documentation_label="Cuenta ARM pendiente de host",
        evidence_urls=[],
        evidence_summary=(
            "El paquete local ARM referencia Sarenet como plataforma auxiliar con host pendiente. "
            "No se debe ejecutar conector hasta resolver URL, alcance CAE y autorizacion tecnica."
        ),
        integration_surface=["auxiliary_platform_review_required", "pending_host"],
        next_action="Mantener configurada como bloqueada hasta que ARM confirme URL/host y alcance operativo.",
        confidence="internal_contract_bundle",
    ),
}


def _manual_export_method(notes: str | None = None) -> PlatformConnectionMethodItem:
    return PlatformConnectionMethodItem(
        method_key="manual_export",
        connector_type="manual_export",
        connector_key="connector_manual_export",
        status="available_internal",
        implemented=True,
        notes=notes
        or "Genera paquete ZIP/checklist para carga manual. No escribe ni lee en la plataforma externa.",
    )


def _official_api_method(status: str, notes: str) -> PlatformConnectionMethodItem:
    return PlatformConnectionMethodItem(
        method_key="official_api",
        connector_type="api_official",
        connector_key=None,
        status=status,
        implemented=False,
        notes=notes,
    )


WRITE_RPA_CONNECTOR_KEYS = {
    "ecoordina": "connector_rpa_e_coordina_write",
    "sixconecta": "connector_rpa_seisconecta_write",
    "ctaima_cae": "connector_rpa_ctaima_write",
    "nomio": "connector_rpa_nomio_write",
    "timenet": "connector_rpa_timenet_write",
    "validate": "connector_rpa_validate_write",
    "vitaly_cae": "connector_rpa_vitaly_cae_write",
}


def _authorized_rpa_method(platform_key: str | None = None) -> PlatformConnectionMethodItem:
    connector_key = WRITE_RPA_CONNECTOR_KEYS.get(platform_key or "")
    if connector_key is not None:
        return PlatformConnectionMethodItem(
            method_key="authorized_rpa",
            connector_type="authorized_rpa_write",
            connector_key=connector_key,
            status="implemented_preview_blocked_until_mapping_approval",
            implemented=True,
            notes=(
                "Conector RPA de escritura registrado. Prepara preview/auditoria y bloquea ejecucion externa "
                "hasta tener mapeos aprobados, captura editable validada y autorizacion humana."
            ),
        )
    return PlatformConnectionMethodItem(
        method_key="authorized_rpa",
        connector_type="authorized_rpa",
        connector_key=None,
        status="disabled_requires_contract_and_manifest",
        implemented=False,
        notes="Deshabilitado. Requiere autorizacion contractual, manifiesto aprobado, preflight y revision humana.",
    )


def _konvergia_method(status: str, notes: str) -> PlatformConnectionMethodItem:
    return PlatformConnectionMethodItem(
        method_key="konvergia_network",
        connector_type="konvergia_network",
        connector_key=None,
        status=status,
        implemented=False,
        notes=notes,
    )


def _commercial_platform(
    *,
    platform_key: str,
    name: str,
    status: str,
    notes: str,
    api_status: str,
    api_notes: str,
    konvergia: PlatformConnectionMethodItem | None = None,
) -> PlatformCatalogItem:
    methods = [
        _manual_export_method(),
        _official_api_method(api_status, api_notes),
        _authorized_rpa_method(platform_key),
    ]
    if konvergia is not None:
        methods.append(konvergia)
    return PlatformCatalogItem(
        platform_key=platform_key,
        name=name,
        status=status,
        is_commercial=True,
        notes=notes,
        methods=methods,
    )


def default_platform_catalog() -> list[PlatformCatalogItem]:
    catalog = [
        PlatformCatalogItem(
            platform_key="mock_cae",
            name="Plataforma Mock CAE",
            status="available",
            is_commercial=False,
            notes="Mock local para probar alta de datos, mapeos y exportaciones sin sistema externo.",
            methods=[
                PlatformConnectionMethodItem(
                    method_key="demo_simulation",
                    connector_type="demo",
                    connector_key="connector_demo",
                    status="available",
                    implemented=True,
                    notes="Simula estados y respuestas locales para validar el contrato interno.",
                ),
                PlatformConnectionMethodItem(
                    method_key="manual_export",
                    connector_type="manual_export",
                    connector_key="connector_manual_export",
                    status="available",
                    implemented=True,
                    notes="Genera preparacion manual sin escribir en ningun sistema externo.",
                ),
            ],
        ),
        _commercial_platform(
            platform_key="dokify",
            name="Dokify",
            status="researched_api_declared",
            notes="Plataforma CAE/compliance del grupo Once For All. Catalogada para futuros conectores autorizados.",
            api_status="official_api_public_product",
            api_notes=(
                "El proveedor anuncia API documentada con referencias, ejemplos, buscador y entidades "
                "Checkin, Employee, Group, Client, Machine, Company, Document y User. Requiere licencia/acceso."
            ),
            konvergia=_konvergia_method(
                "declared_by_provider",
                "Proveedor integrado en la red Konvergia para distribucion documental entre plataformas asociadas.",
            ),
        ),
        _commercial_platform(
            platform_key="nalanda",
            name="Nalanda Global",
            status="researched_integration_declared",
            notes="Plataforma CAE de gran red para construccion, industria y servicios. Pertenece al ecosistema Once For All.",
            api_status="api_service_declared_private_docs",
            api_notes=(
                "El proveedor declara integracion informatica con ERP y el status publico separa CAE Construction API; "
                "la referencia tecnica no esta abierta sin acceso."
            ),
            konvergia=_konvergia_method(
                "declared_by_provider",
                "Nalanda declara integracion con Konvergia para conectar documentacion con otras plataformas CAE.",
            ),
        ),
        _commercial_platform(
            platform_key="konvergia",
            name="Konvergia",
            status="researched_network",
            notes="Red de interoperabilidad CAE para distribuir documentos entre plataformas asociadas.",
            api_status="network_access_private",
            api_notes=(
                "No se ha localizado referencia API publica. La documentacion comercial describe alta, envio/recepcion "
                "y consulta de estados desde el servicio Konvergia."
            ),
        ),
        _commercial_platform(
            platform_key="ctaima_cae",
            name="CTAIMA / Twind",
            status="researched_developer_portal",
            notes="Suite de gestion de contratistas/CAE del grupo CTAIMA, actualmente comunicada tambien como Twind.",
            api_status="developer_portal_public_index_private_specs",
            api_notes=(
                "Existe portal oficial de desarrollador sobre Azure API Management, catalogo de APIs y productos "
                "con limites de peticiones. La documentacion tecnica requiere cuenta."
            ),
        ),
        _commercial_platform(
            platform_key="sixconecta",
            name="6conecta",
            status="researched_api_declared",
            notes="Software CAE/PRL con control de accesos y socio fundador de Konvergia.",
            api_status="api_declared_private_docs",
            api_notes=(
                "La web declara API para integraciones con control de accesos, compras, usuarios/autenticacion y BI; "
                "no hay referencia tecnica publica localizada."
            ),
            konvergia=_konvergia_method(
                "declared_by_provider",
                "6conecta declara integracion con Konvergia para enviar documentacion a plataformas asociadas.",
            ),
        ),
        _commercial_platform(
            platform_key="metacontratas",
            name="Metacontratas",
            status="researched_integration_declared",
            notes="Plataforma CAE de Metadata con validacion documental, control documental y soporte de acceso unico.",
            api_status="integration_declared_private_docs",
            api_notes=(
                "Se declaran conectividad e integracion avanzada en material comercial, pero no se ha encontrado "
                "referencia API publica."
            ),
            konvergia=_konvergia_method(
                "historical_partner_declared",
                "Konvergia cita Metacontratas entre las plataformas principales que participaron en la red.",
            ),
        ),
        _commercial_platform(
            platform_key="ecoordina",
            name="e-coordina",
            status="researched_service_web_declared",
            notes="Plataforma CAE/PRL con presencia internacional, servicio web, URL de integracion y sincronizaciones.",
            api_status="service_web_documented_commercially",
            api_notes=(
                "La documentacion publica describe servicio web para consultar informacion y ejecutar acciones como "
                "alta de trabajadores/empresas, URLs CSV/JSON/XML y sincronizaciones externas."
            ),
            konvergia=_konvergia_method(
                "declared_by_provider",
                "e-coordina declara adhesion a Konvergia para intercambio automatico de documentos.",
            ),
        ),
        _commercial_platform(
            platform_key="ecogestor",
            name="EcoGestor CAE",
            status="researched_api_declared",
            notes="Plataforma CAE de Eurofins EcoGestor para PRL, cumplimiento y control de accesos.",
            api_status="api_and_web_service_declared_private_docs",
            api_notes=(
                "El proveedor declara integracion mediante APIs y web service para plataformas de acceso, barreras y tornos; "
                "no hay referencia tecnica publica localizada."
            ),
            konvergia=_konvergia_method(
                "historical_partner_declared",
                "Konvergia cita EcoGestor entre las plataformas principales de la red.",
            ),
        ),
        _commercial_platform(
            platform_key="egestiona",
            name="eGestiona / eIntegra",
            status="researched_api_declared",
            notes="Plataforma modular CAE/PRL con eIntegra API y API eData Sync.",
            api_status="api_declared_private_docs",
            api_notes=(
                "La web declara eIntegra API y API eData Sync para integrar datos de la plataforma con aplicaciones internas; "
                "no se ha localizado referencia publica."
            ),
        ),
        _commercial_platform(
            platform_key="ucae",
            name="UCAE",
            status="researched_konvergia_declared",
            notes="Plataforma CAE en la nube con UCAE Empresas, UCAE Plus, control de accesos y version movil.",
            api_status="no_public_api_found",
            api_notes=(
                "No se ha localizado referencia API publica. La evidencia publica se centra en CAE, control de accesos, "
                "archivo documental y adhesion a Konvergia."
            ),
            konvergia=_konvergia_method(
                "declared_by_provider",
                "UCAE declara adhesion a Konvergia para intercambio automatico de documentos.",
            ),
        ),
        _commercial_platform(
            platform_key="sgred",
            name="SG Red",
            status="researched_konvergia_declared",
            notes="Plataforma de gestion documental CAE y control de accesos con enfoque de servicio gestionado.",
            api_status="no_public_api_found",
            api_notes=(
                "No se ha localizado referencia API publica. El sitio declara interoperabilidad mediante Konvergia "
                "e integracion con perifericos/control de accesos."
            ),
            konvergia=_konvergia_method(
                "declared_by_provider",
                "SG Red declara interoperabilidad entre plataformas asociadas mediante Konvergia.",
            ),
        ),
        _commercial_platform(
            platform_key="sicondoc_construred",
            name="Sicondoc / Construred",
            status="researched_platform",
            notes="Solucion CAE orientada a documentacion de proveedores/subcontratistas, acceso y control horario.",
            api_status="no_public_api_found",
            api_notes=(
                "No se ha localizado referencia API publica. La web describe gestion documental CAE, control de accesos, "
                "trabajadores, maquinaria y vehiculos."
            ),
        ),
        _commercial_platform(
            platform_key="validate",
            name="Validate",
            status="researched_web_service_declared",
            notes="Software CAE con revision documental, hash documental y control de accesos.",
            api_status="web_service_access_status_declared",
            api_notes=(
                "El proveedor declara Servicio Web gratuito para consultar en linea datos y situacion de acceso de trabajadores "
                "desde sistemas de control de accesos."
            ),
        ),
        _commercial_platform(
            platform_key="tdoc",
            name="tdoc",
            status="researched_platform",
            notes="Plataforma CAE de TESICNOR para entrega/validacion documental y tdoc Access.",
            api_status="no_public_api_found",
            api_notes=(
                "No se ha localizado referencia API publica oficial. El centro de ayuda documenta acceso web y operaciones "
                "de importacion/gestion, pero no un contrato de API."
            ),
        ),
        _commercial_platform(
            platform_key="obralia",
            name="Obralia / Nalanda construccion",
            status="researched_legacy_integration_declared",
            notes="Comunidad/vertical historico de construccion asociado a Nalanda; util para clientes de obra.",
            api_status="xml_integration_declared_legacy",
            api_notes=(
                "La pagina publica historica de Obralia/Nalanda declara XML desarrollado para integraciones ERP; "
                "no se ha localizado referencia API moderna publica."
            ),
        ),
        _commercial_platform(
            platform_key="koordinatu",
            name="Koordinatu",
            status="researched_platform_observed_arm",
            notes="Familia de subdominios Koordinatu observada en cuentas ARM.",
            api_status="no_public_api_found",
            api_notes=(
                "No se ha localizado API publica. Las URLs ARM se mantienen como candidatas a manual_export "
                "hasta que el proveedor entregue documentacion oficial."
            ),
        ),
        _commercial_platform(
            platform_key="iedoce",
            name="ieDOCe",
            status="researched_platform",
            notes="Plataforma web CAE de gestion documental, requisitos, empresas, trabajadores, equipos y accesos.",
            api_status="no_public_api_found",
            api_notes=(
                "La web publica describe plataforma CAE y validaciones, pero no expone contrato API publico."
            ),
        ),
        _commercial_platform(
            platform_key="asemwebservices_integra",
            name="Integra / Asem Web Services",
            status="researched_platform_observed_arm",
            notes="Portal Integra observado en cuentas ARM sobre integra.asemwebservices.es.",
            api_status="no_public_api_found",
            api_notes="No se ha localizado API publica ni proveedor tecnico confirmado desde fuentes abiertas.",
        ),
        _commercial_platform(
            platform_key="sgs_gestiona",
            name="SGS Gestiona",
            status="researched_platform_observed_arm",
            notes="Portal sgs-gestiona observado en cuentas ARM.",
            api_status="no_public_api_found",
            api_notes="No se ha localizado especificacion API publica para este portal.",
        ),
        _commercial_platform(
            platform_key="folyo",
            name="Folyo",
            status="researched_platform_observed_arm",
            notes="Portal Folyo observado en cuentas ARM para entorno CLIENTE_J.",
            api_status="no_public_api_found",
            api_notes="No se ha localizado documentacion API publica.",
        ),
        _commercial_platform(
            platform_key="vitaly_cae",
            name="Vitaly CAE",
            status="researched_platform",
            notes="Servicio CAE de Vitaly observado en cuentas ARM.",
            api_status="no_public_api_found",
            api_notes="No se ha localizado API publica oficial; cualquier integracion requiere guia autorizada.",
        ),
        _commercial_platform(
            platform_key="smartosh",
            name="SmartOSH",
            status="researched_integration_declared",
            notes="Plataforma de gestion avanzada de seguridad y salud con modulo CAE.",
            api_status="integration_declared_private_docs",
            api_notes=(
                "La web declara integracion de sistemas de gestion, pero no publica endpoints ni contrato API."
            ),
        ),
        _commercial_platform(
            platform_key="timenet",
            name="Timenet / GPI Software",
            status="researched_api_declared",
            notes="Aplicacion de registro horario y gestion con modulo avanzado/API de conexion.",
            api_status="api_declared_private_docs",
            api_notes=(
                "Timenet/GPI declara API de conexion, SDK para terceros e importacion/exportacion Excel/CSV/JSON; "
                "requiere kit/documentacion privada."
            ),
        ),
        _commercial_platform(
            platform_key="nomio",
            name="Nomio",
            status="researched_platform_observed_arm",
            notes="Programa web de nominas observado en cuentas ARM; contiene datos laborales sensibles.",
            api_status="no_public_api_found",
            api_notes="No se ha localizado API publica; no crear conector sin contrato oficial y evaluacion RGPD.",
        ),
        _commercial_platform(
            platform_key="coordinaplus",
            name="CoordinaPlus / Adding Plus",
            status="researched_integration_declared",
            notes="Plataforma CAE con equipo PRL y servicios de apoyo operativo.",
            api_status="integration_declared_private_docs",
            api_notes=(
                "La web declara integracion de la CAE con ERP y control de accesos, sin publicar referencia tecnica abierta."
            ),
        ),
        _commercial_platform(
            platform_key="quioo",
            name="Quioo / Quironprevencion",
            status="researched_platform",
            notes="Plataforma CAE avanzada para gestion documental corporativa y contratistas.",
            api_status="no_public_api_found",
            api_notes=(
                "No se ha localizado referencia API publica. La web describe servicios CAE, documentos para firma, "
                "CAE inversa y consulta movil de estados."
            ),
        ),
        _commercial_platform(
            platform_key="sarenet",
            name="Sarenet",
            status="blocked_pending_host",
            notes="Plataforma auxiliar detectada en cuentas ARM; bloqueada hasta confirmar URL/host y alcance CAE.",
            api_status="no_cae_api_confirmed",
            api_notes="No hay host estable en el paquete ARM; queda solo como configuracion bloqueada revisable.",
        ),
    ]
    for item in catalog:
        item.technical_research = TECHNICAL_RESEARCH[item.platform_key]
    return catalog
