from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StandardLabel:
    key: str
    category: str
    entity_scope: str
    display_name: str
    description: str
    data_type: str


@dataclass(frozen=True)
class ExtractedLabel:
    label_kind: str
    raw_label: str
    normalized_label: str
    page_label: str | None
    entity_scope: str | None
    standard_key: str | None
    confidence: int
    metadata: dict[str, Any]


STANDARD_LABELS: tuple[StandardLabel, ...] = (
    StandardLabel("company.name", "identity", "company", "Empresa", "Nombre o razon social de empresa.", "text"),
    StandardLabel("company.tax_id", "identity", "company", "CIF/NIF empresa", "Identificador fiscal de empresa.", "text"),
    StandardLabel("company.address", "identity", "company", "Domicilio", "Direccion postal de empresa.", "text"),
    StandardLabel("company.contact_email", "identity", "company", "Email contacto", "Correo de contacto de empresa.", "email"),
    StandardLabel("company.phone", "identity", "company", "Telefono", "Telefono de empresa o contacto.", "text"),
    StandardLabel("company.activity_cnae", "identity", "company", "CNAE/actividad", "Actividad o CNAE de empresa.", "text"),
    StandardLabel("work_center.name", "assignment", "work_center", "Centro", "Centro de trabajo o centro externo.", "text"),
    StandardLabel("project.name", "assignment", "project", "Obra/proyecto", "Obra, contrato o proyecto externo.", "text"),
    StandardLabel("coordination.name", "assignment", "coordination", "Coordinacion", "Coordinacion, contratacion o relacion CAE externa.", "text"),
    StandardLabel("worker.full_name", "identity", "worker", "Trabajador", "Nombre completo de trabajador.", "text"),
    StandardLabel("worker.first_name", "identity", "worker", "Nombre", "Nombre de trabajador.", "text"),
    StandardLabel("worker.last_name", "identity", "worker", "Apellidos", "Apellidos de trabajador.", "text"),
    StandardLabel("worker.identifier_value", "identity", "worker", "DNI/NIE", "Documento identificativo del trabajador.", "text"),
    StandardLabel("worker.identifier_expires_at", "date", "worker", "Caducidad DNI/NIE", "Fecha de caducidad del identificador.", "date"),
    StandardLabel("worker.social_security_number", "identity", "worker", "NAF/SS", "Numero de afiliacion o seguridad social.", "text"),
    StandardLabel("worker.email", "identity", "worker", "Email trabajador", "Correo de contacto del trabajador.", "email"),
    StandardLabel("worker.phone", "identity", "worker", "Telefono trabajador", "Telefono del trabajador.", "text"),
    StandardLabel("worker.birth_date", "date", "worker", "Fecha nacimiento", "Fecha de nacimiento del trabajador.", "date"),
    StandardLabel("worker.nationality", "identity", "worker", "Nacionalidad", "Nacionalidad del trabajador.", "text"),
    StandardLabel("worker.work_position", "assignment", "worker", "Puesto", "Puesto o perfil asignado.", "text"),
    StandardLabel("worker.starts_at", "date", "worker", "Alta", "Fecha de alta o inicio.", "date"),
    StandardLabel("worker.ends_at", "date", "worker", "Baja", "Fecha de baja o fin.", "date"),
    StandardLabel("worker.contract_type", "assignment", "worker", "Contrato", "Tipo de contrato o relacion laboral.", "text"),
    StandardLabel("worker.medical_fitness_status", "health_minimal", "worker", "Aptitud", "Estado de aptitud laboral sin datos clinicos.", "text"),
    StandardLabel("worker.medical_fitness_expires_at", "health_minimal", "worker", "Caducidad aptitud", "Caducidad de aptitud laboral.", "date"),
    StandardLabel("document.type", "document", "document", "Tipo documental", "Tipo o requisito documental externo.", "text"),
    StandardLabel("document.file", "document", "document", "Fichero", "Archivo documental a subir.", "file"),
    StandardLabel("document.issued_at", "date", "document", "Fecha emision", "Fecha de emision documental.", "date"),
    StandardLabel("document.expires_at", "date", "document", "Fecha caducidad", "Fecha de caducidad documental.", "date"),
    StandardLabel("document.requested_at", "date", "document", "Fecha solicitud", "Fecha en que se solicita el documento.", "date"),
    StandardLabel("document.deadline_at", "date", "document", "Fecha limite", "Fecha limite externa.", "date"),
    StandardLabel("document.received_at", "date", "document", "Fecha recibido", "Fecha de recepcion o cumplimentacion.", "date"),
    StandardLabel("document.validated_at", "date", "document", "Fecha validacion", "Fecha de validacion/verificacion externa.", "date"),
    StandardLabel("document.external_id", "document", "document", "ID documento externo", "Identificador externo de documento o solicitud.", "text"),
    StandardLabel("document.status", "status", "document", "Estado documental", "Estado externo de validacion documental.", "text"),
    StandardLabel("document.rejection_reason", "status", "document", "Motivo rechazo", "Motivo externo de rechazo documental.", "text"),
    StandardLabel("document.incident_flag", "status", "document", "Incidentado", "Indicador de incidencia documental.", "boolean"),
    StandardLabel("machine.record", "asset", "machine", "Maquina/equipo", "Ficha de maquina o equipo.", "record"),
    StandardLabel("asset.identifier", "asset", "asset", "Identificador activo", "Identificador de maquinaria, vehiculo o equipo.", "text"),
    StandardLabel("asset.type", "asset", "asset", "Tipo activo", "Tipo de activo: maquinaria, vehiculo o equipo.", "text"),
    StandardLabel("machine.code", "asset", "machine", "Codigo equipo", "Codigo externo o interno del equipo.", "text"),
    StandardLabel("machine.manufacturer", "asset", "machine", "Fabricante", "Fabricante de maquina/equipo.", "text"),
    StandardLabel("machine.model", "asset", "machine", "Modelo", "Modelo de maquina/equipo.", "text"),
    StandardLabel("machine.serial", "asset", "machine", "Serie", "Numero de serie de maquina/equipo.", "text"),
    StandardLabel("vehicle.record", "asset", "vehicle", "Vehiculo", "Ficha de vehiculo.", "record"),
    StandardLabel("vehicle.plate", "asset", "vehicle", "Matricula", "Matricula de vehiculo.", "text"),
    StandardLabel("chemical_product.record", "asset", "chemical_product", "Producto quimico", "Ficha de producto o sustancia quimica.", "record"),
    StandardLabel("period.start_date", "date", "period", "Desde", "Fecha de inicio de periodo.", "date"),
    StandardLabel("period.end_date", "date", "period", "Hasta", "Fecha de fin de periodo.", "date"),
    StandardLabel("attendance.checks", "time_tracking", "attendance", "Marcajes", "Marcajes o control horario.", "record"),
    StandardLabel("platform.login.username", "access", "platform", "Usuario", "Campo de usuario de acceso.", "text"),
    StandardLabel("platform.login.password", "access", "platform", "Password", "Campo password de acceso, nunca persistir valor.", "password"),
)

STANDARD_LABELS_BY_KEY = {item.key: item for item in STANDARD_LABELS}

SKIPPED_INPUT_TYPES = {"hidden", "password"}
SKIPPED_LABEL_FRAGMENTS = {
    "access denied",
    "acceso denegado",
    "password",
    "token",
    "requestverificationtoken",
    "csrf",
    "cookie",
    "sesion",
    "logout",
    "salir",
    "cargando",
}


def extract_labels_from_capture(structure: dict[str, Any]) -> list[ExtractedLabel]:
    labels: list[ExtractedLabel] = []
    pages = structure.get("pages")
    if not isinstance(pages, list):
        return labels
    seen: set[tuple[str, str, str | None]] = set()
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_label = _clean_text(str(page.get("label") or page.get("title") or ""))
        page_context = " ".join(
            part
            for part in [
                page_label,
                str(page.get("title") or ""),
                " ".join(_string_list(page.get("headings"))),
            ]
            if part
        )
        for heading in _string_list(page.get("headings")):
            _append_label(labels, seen, "heading", heading, page_label, page_context, {"source": "heading"})
        for nav_label in _string_list(page.get("nav_labels")):
            _append_label(labels, seen, "nav", nav_label, page_label, page_context, {"source": "nav"})
        for button in page.get("buttons") or []:
            if not isinstance(button, dict):
                continue
            raw = _first_nonempty(button.get("text"), button.get("itemId"), button.get("id"), button.get("name"))
            if raw:
                _append_label(labels, seen, "button", raw, page_label, page_context, {"source": "page_button"})
        for headers in page.get("table_headers") or []:
            if not isinstance(headers, list):
                continue
            for header in _string_list(headers):
                _append_label(labels, seen, "table_header", header, page_label, page_context, {"source": "table"})
        for header in _string_list(page.get("grid_headers")):
            _append_label(labels, seen, "grid_header", header, page_label, page_context, {"source": "grid_header"})
        for grid_index, grid in enumerate(page.get("grid_columns") or []):
            if not isinstance(grid, dict):
                continue
            for column in grid.get("columns") or []:
                if not isinstance(column, dict):
                    continue
                raw = _first_nonempty(column.get("header"), column.get("data_index"))
                if raw:
                    _append_label(
                        labels,
                        seen,
                        "grid_column",
                        raw,
                        page_label,
                        page_context,
                        {
                            "source": "grid_column",
                            "grid_index": grid_index,
                            "data_index": column.get("data_index"),
                            "hidden": column.get("hidden"),
                        },
                    )
            for field in _string_list(grid.get("store_fields")):
                _append_label(
                    labels,
                    seen,
                    "grid_store_field",
                    field,
                    page_label,
                    page_context,
                    {"source": "grid_store_field", "grid_index": grid_index},
                )
        for status_column in page.get("status_column_counts") or []:
            if not isinstance(status_column, dict):
                continue
            for value in status_column.get("values") or []:
                if not isinstance(value, dict):
                    continue
                raw = value.get("status_text")
                if raw:
                    _append_label(
                        labels,
                        seen,
                        "status_value",
                        str(raw),
                        page_label,
                        page_context,
                        {"source": "status_column", "field": status_column.get("field"), "count": value.get("count")},
                    )
        for form_index, form in enumerate(page.get("forms") or []):
            if not isinstance(form, dict):
                continue
            form_meta = {
                "source": "form",
                "method": form.get("method"),
                "action": _safe_action(form.get("action") or form.get("action_host")),
                "form_index": form_index,
            }
            for input_item in form.get("inputs") or []:
                if not isinstance(input_item, dict):
                    continue
                input_type = str(input_item.get("type") or "").lower()
                if input_type in SKIPPED_INPUT_TYPES:
                    continue
                raw = _first_nonempty(
                    input_item.get("fieldLabel"),
                    input_item.get("field_label"),
                    input_item.get("ariaLabel"),
                    input_item.get("aria_label"),
                    input_item.get("placeholder"),
                    input_item.get("name"),
                    input_item.get("id"),
                )
                if raw:
                    _append_label(
                        labels,
                        seen,
                        "form_field",
                        raw,
                        page_label,
                        page_context,
                        form_meta | {"tag": input_item.get("tag"), "type": input_type, "required": input_item.get("required")},
                    )
            for button in form.get("buttons") or []:
                if not isinstance(button, dict):
                    continue
                raw = _first_nonempty(button.get("text"), button.get("name"), button.get("id"))
                if raw:
                    _append_label(labels, seen, "button", raw, page_label, page_context, form_meta | {"source": "button"})
        for field in page.get("fields") or []:
            if not isinstance(field, dict):
                continue
            raw = _first_nonempty(field.get("fieldLabel"), field.get("emptyText"), field.get("name"), field.get("id"))
            if raw:
                _append_label(
                    labels,
                    seen,
                    "form_field",
                    raw,
                    page_label,
                    page_context,
                    {
                        "source": "page_field",
                        "type": field.get("type") or field.get("xtype"),
                        "name": field.get("name"),
                    },
                )
    for action in structure.get("navigation_actions") or []:
        if not isinstance(action, dict):
            continue
        raw = _first_nonempty(action.get("label"), action.get("item_id"))
        if raw:
            _append_label(labels, seen, "nav_action", raw, None, "", {"source": "navigation_action"})
    return labels


def standard_label_payloads() -> list[dict[str, str]]:
    return [
        {
            "key": item.key,
            "category": item.category,
            "entity_scope": item.entity_scope,
            "display_name": item.display_name,
            "description": item.description,
            "data_type": item.data_type,
        }
        for item in STANDARD_LABELS
    ]


def normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(character for character in normalized if not unicodedata.combining(character))
    ascii_value = re.sub(r"[^a-zA-Z0-9]+", " ", ascii_value)
    return re.sub(r"\s+", " ", ascii_value).strip().lower()


def infer_standard_label(raw_label: str, *, page_context: str = "", label_kind: str = "") -> tuple[str | None, str | None, int]:
    raw_norm = normalize_label(raw_label)
    context_norm = normalize_label(page_context)
    combined = f"{raw_norm} {context_norm}".strip()
    if not raw_norm or any(fragment in raw_norm for fragment in SKIPPED_LABEL_FRAGMENTS):
        return None, None, 0
    entity_scope = _infer_entity_scope(combined)
    direct: list[tuple[str, str | None, int, tuple[str, ...]]] = [
        ("platform.login.username", "platform", 96, ("usuario", "username", "input login", "txt usuario", "input.login", "user")),
        ("platform.login.password", "platform", 96, ("password", "contrasena", "txt password", "input.password")),
        ("worker.identifier_value", "worker", 94, ("dni", "nie", "nif trabajador", "documento trabajador", "jform nif", "pasaporte")),
        ("company.tax_id", "company", 92, ("cif", "nif empresa", "tax id")),
        ("company.address", "company", 84, ("domicilio", "direccion", "address")),
        ("company.contact_email", "company", 84, ("email contacto", "correo contacto")),
        ("company.phone", "company", 82, ("telefono", "phone", "movil")),
        ("company.activity_cnae", "company", 80, ("cnae", "actividad")),
        ("worker.first_name", "worker", 90, ("nombre", "jform nombre")),
        ("worker.last_name", "worker", 90, ("apellidos", "apellido", "jform apellidos")),
        ("worker.email", "worker", 84, ("email trabajador", "correo trabajador", "email")),
        ("worker.phone", "worker", 82, ("telefono trabajador", "movil trabajador")),
        ("worker.social_security_number", "worker", 88, ("naf", "seguridad social", "ss", "nuss")),
        ("worker.birth_date", "worker", 82, ("fecha nacimiento", "nacimiento")),
        ("worker.nationality", "worker", 86, ("nacionalidad", "pais")),
        ("worker.work_position", "worker", 86, ("puesto", "perfil")),
        ("worker.starts_at", "worker", 82, ("fecha alta", "alta")),
        ("worker.ends_at", "worker", 82, ("fecha baja", "baja")),
        ("worker.contract_type", "worker", 80, ("contrato", "tipo contrato")),
        ("worker.identifier_expires_at", "worker", 85, ("caducidad dni", "caducidad nie")),
        ("worker.medical_fitness_status", "worker", 80, ("aptitud", "reconocimiento medico", "vigilancia salud")),
        ("worker.medical_fitness_expires_at", "worker", 80, ("caducidad aptitud", "caducidad reconocimiento")),
        ("company.name", "company", 88, ("razon social", "empresa", "nombre empresa")),
        ("work_center.name", "work_center", 88, ("centro", "centro de trabajo")),
        ("coordination.name", "coordination", 84, ("coordinacion", "contratacion")),
        ("project.name", "project", 84, ("obra", "proyecto", "contrato")),
        ("worker.full_name", "worker", 86, ("trabajador", "empleado", "empleados")),
        ("document.file", "document", 86, ("fichero", "archivo", "file", "upload", "excel file", "documentacion file")),
        ("document.issued_at", "document", 82, ("fecha emision", "f emision", "emision")),
        ("document.expires_at", "document", 86, ("fecha caducidad", "f caducidad", "caducidad", "vence")),
        ("document.requested_at", "document", 82, ("fecha solicitado", "f solicitado", "solicitado")),
        ("document.deadline_at", "document", 82, ("fecha limite", "f limite", "limite")),
        ("document.received_at", "document", 82, ("fecha recibido", "f recibido", "cumplimentado")),
        ("document.validated_at", "document", 82, ("fecha validado", "fecha verificado", "f validado", "f verificado", "verificado")),
        ("document.external_id", "document", 82, ("documento id", "documentacion id")),
        ("document.status", "document", 82, ("estado documental", "documentacion estado", "estado", "validacion", "validado", "caducado")),
        ("document.rejection_reason", "document", 86, ("motivo rechazo", "rechazo", "incidencia")),
        ("document.incident_flag", "document", 80, ("incidentado",)),
        ("document.type", "document", 82, ("tipo documento", "tipo doc", "documento tipo", "documentacion", "inter documentacion", "requisito")),
        ("machine.record", "machine", 90, ("maquinas equipos", "maquina", "equipamiento", "equipo")),
        ("asset.identifier", "asset", 82, ("identificador interno", "asset identifier")),
        ("asset.type", "asset", 82, ("tipo activo", "tipo maquinaria", "tipo vehiculo")),
        ("machine.code", "machine", 86, ("codigo equipo", "codigo")),
        ("machine.manufacturer", "machine", 86, ("fabricante",)),
        ("machine.model", "machine", 86, ("modelo",)),
        ("machine.serial", "machine", 86, ("serie", "numero serie")),
        ("vehicle.record", "vehicle", 88, ("vehiculo", "vehiculos")),
        ("vehicle.plate", "vehicle", 88, ("matricula",)),
        ("chemical_product.record", "chemical_product", 84, ("producto quimico", "sustancia quimica", "pq")),
        ("period.start_date", "period", 84, ("fecha desde", "desde", "baja")),
        ("period.end_date", "period", 84, ("fecha hasta", "hasta", "alta")),
        ("attendance.checks", "attendance", 88, ("marcajes", "control de marcajes")),
    ]
    for key, scope, confidence, needles in direct:
        if any(_has_label_keyword(raw_norm, needle) for needle in needles):
            return key, scope or entity_scope, _adjust_confidence(confidence, label_kind, raw_norm)
    return None, entity_scope, 35 if entity_scope else 0


def _append_label(
    labels: list[ExtractedLabel],
    seen: set[tuple[str, str, str | None]],
    label_kind: str,
    raw_label: str,
    page_label: str | None,
    page_context: str,
    metadata: dict[str, Any],
) -> None:
    cleaned = _clean_text(raw_label)
    normalized = normalize_label(cleaned)
    if not cleaned or not normalized or any(fragment in normalized for fragment in SKIPPED_LABEL_FRAGMENTS):
        return
    key = (label_kind, normalized, page_label)
    if key in seen:
        return
    seen.add(key)
    standard_key, entity_scope, confidence = infer_standard_label(cleaned, page_context=page_context, label_kind=label_kind)
    labels.append(
        ExtractedLabel(
            label_kind=label_kind,
            raw_label=cleaned,
            normalized_label=normalized,
            page_label=page_label,
            entity_scope=entity_scope,
            standard_key=standard_key,
            confidence=confidence,
            metadata=metadata,
        )
    )


def _infer_entity_scope(value: str) -> str | None:
    if any(term in value for term in ("trabajador", "empleado", "empleados", "apellidos", "nacionalidad")):
        return "worker"
    if any(term in value for term in ("empresa", "razon social", "cif")):
        return "company"
    if any(term in value for term in ("document", "fichero", "archivo", "requisito")):
        return "document"
    if any(term in value for term in ("coordinacion", "contratacion")):
        return "coordination"
    if any(term in value for term in ("maquina", "equipo", "equipamiento", "fabricante", "modelo", "serie")):
        return "machine"
    if "vehiculo" in value or "matricula" in value:
        return "vehicle"
    if any(term in value for term in ("producto quimico", "sustancia quimica")):
        return "chemical_product"
    if any(term in value for term in ("marcaje", "ausencia", "vacaciones", "periodo")):
        return "attendance"
    return None


def _adjust_confidence(confidence: int, label_kind: str, raw_norm: str) -> int:
    if label_kind == "form_field":
        confidence += 4
    if label_kind == "nav":
        confidence -= 8
    if len(raw_norm) <= 2:
        confidence -= 20
    return max(0, min(confidence, 100))


def _has_label_keyword(raw_norm: str, needle: str) -> bool:
    needle_norm = normalize_label(needle)
    if not needle_norm:
        return False
    if len(needle_norm) <= 4 or " " not in needle_norm:
        return re.search(rf"\b{re.escape(needle_norm)}\b", raw_norm) is not None
    return needle_norm in raw_norm


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean_text(str(item)) for item in value if _clean_text(str(item))]


def _first_nonempty(*values: object) -> str | None:
    for value in values:
        if value is None:
            continue
        cleaned = _clean_text(str(value))
        if cleaned:
            return cleaned
    return None


def _safe_action(value: object) -> str | None:
    if value is None:
        return None
    cleaned = _clean_text(str(value))
    return cleaned[:240] if cleaned else None
