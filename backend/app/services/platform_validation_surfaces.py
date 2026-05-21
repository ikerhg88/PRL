from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CURRENT_PLATFORM_SLUGS = {
    "ctaima",
    "e_coordina",
    "nomio",
    "seisconecta",
    "timenet",
    "validate",
    "vitaly_cae",
}

PLATFORM_NAMES = {
    "ctaima": "CTAIMA / CTAIMA CAE",
    "e_coordina": "e-coordina",
    "nomio": "Nomio",
    "seisconecta": "6conecta",
    "timenet": "Timenet",
    "validate": "Validate",
    "vitaly_cae": "Vitaly CAE",
    "unknown": "Unknown",
}


@dataclass(frozen=True)
class SurfacePattern:
    use: str
    label: str
    terms: tuple[str, ...]


SURFACE_PATTERNS = (
    SurfacePattern(
        "notification_inbox",
        "Notificaciones / avisos",
        ("notificacion", "notificaciones", "notification", "aviso", "avisos", "alerta", "alerts", "bandeja", "inbox"),
    ),
    SurfacePattern(
        "pending_validation",
        "Pendientes de validacion",
        ("pendiente", "validacion", "validado", "validada", "revision", "revisar", "solicitud", "solicitudes", "homologacion"),
    ),
    SurfacePattern(
        "incident_review",
        "Incidencias / rechazos",
        ("incidencia", "incidencias", "incident", "rechazado", "rechazada", "bloqueado", "bloqueada", "error"),
    ),
    SurfacePattern(
        "worker_readback",
        "Lectura posterior trabajador",
        ("trabajador", "trabajadores", "empleado", "empleados", "dni", "nie", "nif", "listado"),
    ),
    SurfacePattern(
        "document_readback",
        "Lectura posterior documental",
        ("documento", "documentos", "documentacion", "inter documentacion", "subido", "subida", "caducidad", "caducado"),
    ),
    SurfacePattern(
        "access_readback",
        "Lectura accesos / estado global",
        ("consulta accesos", "control de accesos", "estado global", "acceso", "accesos"),
    ),
)

EVIDENCE_CONFIDENCE = {
    "page_title": 86,
    "page_url": 84,
    "nav_label": 82,
    "heading": 80,
    "table_header": 78,
    "button": 72,
    "form_field": 68,
    "network_endpoint_observed": 64,
}

RECOMMENDED_ORDER = {
    "worker_readback": 10,
    "document_readback": 20,
    "pending_validation": 30,
    "notification_inbox": 40,
    "incident_review": 50,
    "access_readback": 60,
}


def build_validation_surface_map(
    *,
    capture_root: Path,
    current_only: bool = True,
) -> dict[str, Any]:
    captures = sorted(capture_root.glob("*/technical_capture.redacted.json"))
    platform_items: dict[str, dict[str, Any]] = {}
    skipped = 0
    for capture_path in captures:
        data = _load_json(capture_path)
        if not data:
            skipped += 1
            continue
        slug = _infer_platform_slug(data)
        if current_only and slug not in CURRENT_PLATFORM_SLUGS:
            skipped += 1
            continue
        platform = platform_items.setdefault(
            slug,
            {
                "platform_slug": slug,
                "platform_name": PLATFORM_NAMES.get(slug, slug),
                "capture_count": 0,
                "captures": [],
                "surfaces": [],
                "summary": {},
                "readback_plan": [],
            },
        )
        platform["capture_count"] += 1
        platform["captures"].append(
            {
                "capture_id": capture_path.parent.name,
                "source_ref": _relative(capture_path),
                "outcome": data.get("outcome"),
                "source": _safe_source(data.get("source")),
            }
        )
        platform["surfaces"].extend(_extract_surfaces(data, capture_id=capture_path.parent.name, source_ref=_relative(capture_path)))

    for platform in platform_items.values():
        platform["surfaces"] = _dedupe_surfaces(platform["surfaces"])
        platform["surfaces"].sort(key=lambda item: (RECOMMENDED_ORDER.get(item["use"], 99), -item["confidence"], item["label"]))
        platform["summary"] = _summary(platform["surfaces"])
        platform["readback_plan"] = _readback_plan(platform["surfaces"])

    platforms = sorted(platform_items.values(), key=lambda item: item["platform_name"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "read_only": True,
            "no_captcha_or_mfa_bypass": True,
            "no_private_api_contract_inferred": True,
            "redacted_evidence_only": True,
            "current_platforms_only": current_only,
        },
        "totals": {
            "capture_files_seen": len(captures),
            "capture_files_used": sum(item["capture_count"] for item in platforms),
            "capture_files_skipped": skipped,
            "platforms": len(platforms),
            "surfaces": sum(len(item["surfaces"]) for item in platforms),
        },
        "platforms": platforms,
    }


def write_validation_surface_artifacts(payload: dict[str, Any], *, out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "platform_validation_surfaces.redacted.json"
    csv_path = out_dir / "platform_validation_surfaces.redacted.csv"
    md_path = out_dir / "platform_validation_surfaces_summary.redacted.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(payload, csv_path)
    _write_markdown(payload, md_path)
    return {
        "json": _relative(json_path),
        "csv": _relative(csv_path),
        "markdown": _relative(md_path),
    }


def _extract_surfaces(data: dict[str, Any], *, capture_id: str, source_ref: str) -> list[dict[str, Any]]:
    surfaces: list[dict[str, Any]] = []
    for page in data.get("pages") or []:
        page_label = str(page.get("label") or "")
        page_title = str(page.get("title") or "")
        page_url = str(page.get("url_sanitized") or "")
        page_context = {
            "capture_id": capture_id,
            "source_ref": source_ref,
            "page_label": page_label,
            "page_title": page_title,
            "url_sanitized": page_url,
        }
        surfaces.extend(_match_text(page_title, evidence_kind="page_title", page_context=page_context))
        surfaces.extend(_match_text(page_url, evidence_kind="page_url", page_context=page_context))
        for item in page.get("nav_labels") or []:
            surfaces.extend(_match_text(str(item), evidence_kind="nav_label", page_context=page_context))
        for item in page.get("headings") or []:
            surfaces.extend(_match_text(str(item), evidence_kind="heading", page_context=page_context))
        for item in page.get("buttons") or []:
            if isinstance(item, dict):
                label = item.get("text") or item.get("id") or item.get("name") or ""
            else:
                label = item
            surfaces.extend(_match_text(str(label), evidence_kind="button", page_context=page_context))
        for header_row in page.get("table_headers") or []:
            for header in header_row or []:
                surfaces.extend(_match_text(str(header), evidence_kind="table_header", page_context=page_context))
        for header in page.get("grid_headers") or []:
            surfaces.extend(_match_text(str(header), evidence_kind="table_header", page_context=page_context))
        for form in page.get("forms") or []:
            for field in form.get("inputs") or []:
                label = " ".join(str(field.get(key) or "") for key in ("name", "id", "placeholder", "ariaLabel", "aria_label"))
                surfaces.extend(_match_text(label, evidence_kind="form_field", page_context=page_context))

    for section_key in ("requests_sample", "responses_sample"):
        for item in data.get(section_key) or []:
            url = str(item.get("url") or "")
            surfaces.extend(
                _match_text(
                    url,
                    evidence_kind="network_endpoint_observed",
                    page_context={
                        "capture_id": capture_id,
                        "source_ref": source_ref,
                        "page_label": section_key,
                        "page_title": "",
                        "url_sanitized": _sanitize_url(url),
                    },
                )
            )
    return surfaces


def _match_text(text: str, *, evidence_kind: str, page_context: dict[str, str]) -> list[dict[str, Any]]:
    normalized = _norm(text)
    if not normalized:
        return []
    items: list[dict[str, Any]] = []
    for pattern in SURFACE_PATTERNS:
        matched_terms = [term for term in pattern.terms if _norm(term) in normalized]
        if not matched_terms:
            continue
        confidence = min(98, EVIDENCE_CONFIDENCE.get(evidence_kind, 60) + max(0, len(matched_terms) - 1) * 3)
        items.append(
            {
                "use": pattern.use,
                "label": pattern.label,
                "evidence_kind": evidence_kind,
                "matched_terms": matched_terms,
                "candidate_text": _redact_text(text),
                "confidence": confidence,
                **page_context,
                "safe_for_automation": evidence_kind != "network_endpoint_observed",
                "notes": _notes_for(evidence_kind),
            }
        )
    return items


def _readback_plan(surfaces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for use in sorted({item["use"] for item in surfaces}, key=lambda item: RECOMMENDED_ORDER.get(item, 99)):
        candidates = [item for item in surfaces if item["use"] == use]
        if not candidates:
            continue
        primary = candidates[0]
        plan.append(
            {
                "use": use,
                "label": primary["label"],
                "priority": RECOMMENDED_ORDER.get(use, 99),
                "suggested_entry": primary["candidate_text"],
                "page_label": primary["page_label"],
                "url_sanitized": primary["url_sanitized"],
                "evidence_count": len(candidates),
                "operator_message": _operator_message(use),
            }
        )
    return plan


def _summary(surfaces: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in surfaces:
        counts[item["use"]] = counts.get(item["use"], 0) + 1
    return counts


def _dedupe_surfaces(surfaces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for item in surfaces:
        key = (
            item["use"],
            item["evidence_kind"],
            item["candidate_text"],
            item["page_label"],
            item["url_sanitized"],
        )
        if key not in best or item["confidence"] > best[key]["confidence"]:
            best[key] = item
    return list(best.values())


def _infer_platform_slug(data: dict[str, Any]) -> str:
    text_parts: list[str] = []
    source = data.get("source") or {}
    if isinstance(source, dict):
        text_parts.extend(str(source.get(key) or "") for key in ("label", "url", "entry_url", "platform"))
    outcome = data.get("outcome") or {}
    if isinstance(outcome, dict):
        text_parts.extend(str(outcome.get(key) or "") for key in ("initial_url_sanitized", "final_url_sanitized", "initial_title", "final_title"))
    for page in data.get("pages") or []:
        text_parts.extend(str(page.get(key) or "") for key in ("url_sanitized", "title", "label"))
    for item in (data.get("requests_sample") or [])[:80]:
        text_parts.append(str(item.get("url") or ""))
    haystack = _norm(" ".join(text_parts))
    if "6conecta" in haystack or "seysconecta" in haystack:
        return "seisconecta"
    if "e coordina" in haystack or "v5 e coordina" in haystack:
        return "e_coordina"
    if "ctaimacae" in haystack or "ctaima cae" in haystack or "ctaima" in haystack:
        return "ctaima"
    if "nomio" in haystack:
        return "nomio"
    if "timenet" in haystack or "gpisoftware" in haystack:
        return "timenet"
    if "validate network" in haystack or "saas validate" in haystack:
        return "validate"
    if "vitaly" in haystack:
        return "vitaly_cae"
    return "unknown"


def _write_csv(payload: dict[str, Any], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "platform_slug",
                "platform_name",
                "use",
                "label",
                "evidence_kind",
                "candidate_text",
                "confidence",
                "page_label",
                "page_title",
                "url_sanitized",
                "capture_id",
                "safe_for_automation",
                "notes",
            ],
        )
        writer.writeheader()
        for platform in payload.get("platforms") or []:
            for surface in platform.get("surfaces") or []:
                writer.writerow(
                    {
                        "platform_slug": platform["platform_slug"],
                        "platform_name": platform["platform_name"],
                        **{key: surface.get(key) for key in writer.fieldnames if key not in {"platform_slug", "platform_name"}},
                    }
                )


def _write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# Superficies de validacion posterior por plataforma",
        "",
        f"Generado: {payload.get('generated_at')}",
        "",
        "Regla: una escritura externa solo se considera valida cuando hay lectura posterior positiva.",
        "Los endpoints observados son evidencia de superficie tecnica, no contrato API.",
        "",
    ]
    for platform in payload.get("platforms") or []:
        lines.extend(
            [
                f"## {platform['platform_name']}",
                "",
                f"- Capturas usadas: {platform['capture_count']}",
                f"- Superficies detectadas: {len(platform.get('surfaces') or [])}",
                f"- Resumen: {platform.get('summary')}",
                "",
                "| Prioridad | Uso | Entrada sugerida | Pagina | Evidencias |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for step in platform.get("readback_plan") or []:
            lines.append(
                f"| {step['priority']} | {step['label']} | `{step['suggested_entry']}` | "
                f"`{step.get('page_label') or '-'}` | {step['evidence_count']} |"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _operator_message(use: str) -> str:
    return {
        "worker_readback": "Buscar el trabajador por identificador/nombre y confirmar si aparece como alta pendiente, activa o rechazada.",
        "document_readback": "Revisar documentos solicitados/subidos y estados de validacion posteriores.",
        "pending_validation": "Comprobar cola de pendientes, homologacion o solicitudes que requieran validador humano.",
        "notification_inbox": "Revisar avisos/notificaciones posteriores al submit o mensajes del validador.",
        "incident_review": "Revisar incidencias, rechazos o bloqueos generados por la plataforma.",
        "access_readback": "Comprobar estado global/accesos si la plataforma separa acceso de documentacion.",
    }.get(use, "Revisar la superficie detectada en modo solo lectura.")


def _notes_for(evidence_kind: str) -> str:
    if evidence_kind == "network_endpoint_observed":
        return "Endpoint observado en navegador; no implica permiso para API privada."
    return "Superficie de UI observada; usar solo para navegacion read-only o RPA autorizada."


def _safe_source(source: Any) -> dict[str, Any]:
    if not isinstance(source, dict):
        return {}
    return {key: _redact_text(str(value)) for key, value in source.items() if key not in {"password", "secret", "token"}}


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _sanitize_url(value: str) -> str:
    return re.sub(r"([?&][^=&]+)=([^&]+)", r"\1=[value]", value)


def _redact_text(value: str) -> str:
    value = _sanitize_url(value)
    value = re.sub(r"[\w.+-]+@[\w.-]+", "[email]", value)
    value = re.sub(r"\b\d{7,}[A-Za-z]?\b", "[id]", value)
    return re.sub(r"\s+", " ", value).strip()[:180]


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _norm(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(character for character in normalized if not unicodedata.combining(character))
    ascii_value = re.sub(r"[^a-zA-Z0-9]+", " ", ascii_value).strip().lower()
    return re.sub(r"\s+", " ", ascii_value)
