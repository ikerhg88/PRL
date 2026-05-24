from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Company,
    Document,
    DocumentType,
    DocumentVersion,
    PlatformRpaAccountProposal,
    PlatformRpaManifest,
    Worker,
)
from app.services.platform_contracts import CONTRACT_SLUG_TO_PLATFORM_KEY
from app.services.platform_edit_methods import (
    EDITABLE_OPERATION_REQUIRED_KEYS,
    build_platform_edit_methods,
    operation_required_keys,
)

SUPPORTED_PREVIEW_OPERATIONS = tuple(EDITABLE_OPERATION_REQUIRED_KEYS)

FIELD_METHOD_READY_STATUSES = {"ready_for_preview", "credential_secret_only"}


class WritePreviewError(ValueError):
    pass


def build_write_operation_preview(
    session: Session,
    *,
    tenant_id: int,
    account_proposal_id: int,
    operation: str,
    company_id: int | None = None,
    worker_id: int | None = None,
    document_version_id: int | None = None,
) -> dict[str, Any]:
    if operation not in EDITABLE_OPERATION_REQUIRED_KEYS:
        raise WritePreviewError("Operacion de escritura no soportada.")

    account = session.scalar(
        select(PlatformRpaAccountProposal).where(
            PlatformRpaAccountProposal.tenant_id == tenant_id,
            PlatformRpaAccountProposal.id == account_proposal_id,
        )
    )
    if account is None:
        raise WritePreviewError("Cuenta de plataforma no encontrada.")
    manifest = session.scalar(
        select(PlatformRpaManifest).where(
            PlatformRpaManifest.tenant_id == tenant_id,
            PlatformRpaManifest.id == account.manifest_id,
        )
    )
    if manifest is None:
        raise WritePreviewError("Manifiesto de plataforma no encontrado.")
    company = _resolve_company(session, tenant_id=tenant_id, company_id=company_id)
    worker = _resolve_worker(session, tenant_id=tenant_id, worker_id=worker_id, operation=operation)
    version, document, document_type = _resolve_document(
        session,
        tenant_id=tenant_id,
        document_version_id=document_version_id,
        operation=operation,
    )
    if worker is not None and company is not None and worker.company_id != company.id:
        raise WritePreviewError("El trabajador no pertenece a la empresa activa.")
    if document is not None and company is not None:
        _validate_document_company(session, tenant_id=tenant_id, document=document, company_id=company.id)

    edit_catalog = build_platform_edit_methods(
        session,
        tenant_id=tenant_id,
        company_id=company.id if company is not None else None,
        priority_group="all",
    )
    context = _find_edit_context(edit_catalog, manifest_id=manifest.id, account_proposal_id=account.id)
    if context is None:
        raise WritePreviewError("No hay contexto de edicion para esta cuenta.")
    operation_method = _operation_method(context, operation)
    field_methods = {field["standard_key"]: field for field in context.get("field_methods") or []}
    local_values = _local_values(
        company=company,
        worker=worker,
        version=version,
        document=document,
        document_type=document_type,
    )

    fields = []
    blockers: list[dict[str, str]] = []
    for key in operation_required_keys(manifest.platform_slug, operation):
        method = field_methods.get(key)
        value = local_values.get(key)
        field_payload = _field_preview(key=key, operation=operation, method=method, value=value)
        fields.append(field_payload)
        blockers.extend(field_payload["blockers"])

    mapping_ready = not any(blocker["kind"].startswith("mapping_") for blocker in blockers)
    local_data_ready = not any(blocker["kind"] == "local_value_missing" for blocker in blockers)
    account_ready_for_live = account.status == "active"
    preview_ready = mapping_ready and local_data_ready
    status = _preview_status(
        preview_ready=preview_ready,
        mapping_ready=mapping_ready,
        local_data_ready=local_data_ready,
    )

    return {
        "status": status,
        "operation": operation,
        "platform": {
            "manifest_id": manifest.id,
            "platform_slug": manifest.platform_slug,
            "platform_key": CONTRACT_SLUG_TO_PLATFORM_KEY.get(manifest.platform_slug, manifest.platform_slug),
            "platform_name": manifest.platform_name,
            "external_platform_id": manifest.external_platform_id,
        },
        "account": {
            "account_proposal_id": account.id,
            "platform_account_id": account.platform_account_id,
            "external_company_name": account.external_company_name,
            "status": account.status,
            "host": account.host,
            "entry_url_configured": bool(account.entry_url),
            "dry_run": account.dry_run,
            "manual_approval_required": account.manual_approval_required,
        },
        "context_trace_label": context.get("trace_label"),
        "company": {
            "id": company.id if company else None,
            "name": company.name if company else None,
        },
        "entity": _entity_summary(
            operation=operation,
            worker=worker,
            document=document,
            version=version,
            document_type=document_type,
            company=company,
        ),
        "readiness": {
            "preview_ready": preview_ready,
            "mapping_ready": mapping_ready,
            "local_data_ready": local_data_ready,
            "account_ready_for_live": account_ready_for_live,
            "external_write_enabled": False,
            "dry_run_required": True,
            "manual_approval_required": True,
            "before_after_audit_required": True,
        },
        "operation_method": operation_method,
        "fields": fields,
        "blockers": blockers,
        "planned_external_changes": [
            {
                "standard_key": field["standard_key"],
                "display_name": field["display_name"],
                "method": field["method"],
                "value_preview": field["value_preview"],
            }
            for field in fields
            if field["sendable"]
        ],
        "next_action": _next_action(status, account_ready_for_live=account_ready_for_live),
        "policy": {
            "captcha_bypass": False,
            "mfa_bypass": False,
            "stores_static_commercial_selectors": False,
            "stores_only_reviewed_captured_write_paths": True,
            "stores_credentials_or_tokens": False,
            "live_external_write_requires_submit_job": True,
        },
    }


def _resolve_company(session: Session, *, tenant_id: int, company_id: int | None) -> Company | None:
    statement = select(Company).where(Company.tenant_id == tenant_id)
    if company_id is not None:
        statement = statement.where(Company.id == company_id)
    return session.scalars(statement.order_by(Company.id)).first()


def _resolve_worker(
    session: Session,
    *,
    tenant_id: int,
    worker_id: int | None,
    operation: str,
) -> Worker | None:
    if operation not in {"upsert_worker", "deactivate_worker", "upload_worker_document"}:
        return None
    if worker_id is None:
        raise WritePreviewError("worker_id es obligatorio para esta operacion.")
    worker = session.scalar(select(Worker).where(Worker.tenant_id == tenant_id, Worker.id == worker_id))
    if worker is None:
        raise WritePreviewError("Trabajador no encontrado.")
    return worker


def _resolve_document(
    session: Session,
    *,
    tenant_id: int,
    document_version_id: int | None,
    operation: str,
) -> tuple[DocumentVersion | None, Document | None, DocumentType | None]:
    if operation not in {"upload_worker_document", "upload_company_document", "upload_machine_vehicle_document"}:
        return None, None, None
    if document_version_id is None:
        raise WritePreviewError("document_version_id es obligatorio para esta operacion.")
    version = session.get(DocumentVersion, document_version_id)
    if version is None:
        raise WritePreviewError("Version documental no encontrada.")
    document = session.get(Document, version.document_id)
    if document is None or document.tenant_id != tenant_id:
        raise WritePreviewError("Documento no encontrado.")
    document_type = session.get(DocumentType, document.document_type_id)
    return version, document, document_type


def _validate_document_company(
    session: Session,
    *,
    tenant_id: int,
    document: Document,
    company_id: int,
) -> None:
    if document.entity_type == "company":
        if document.entity_id != company_id:
            raise WritePreviewError("El documento no pertenece a la empresa activa.")
        return
    if document.entity_type == "worker":
        worker = session.scalar(select(Worker).where(Worker.tenant_id == tenant_id, Worker.id == document.entity_id))
        if worker is None or worker.company_id != company_id:
            raise WritePreviewError("El documento no pertenece a un trabajador de la empresa activa.")
        return
    raise WritePreviewError("Tipo de entidad documental no soportado para escritura externa.")


def _find_edit_context(
    catalog: dict[str, Any],
    *,
    manifest_id: int,
    account_proposal_id: int,
) -> dict[str, Any] | None:
    fallback: dict[str, Any] | None = None
    contexts = catalog.get("contexts")
    if not isinstance(contexts, list):
        return None
    for context in contexts:
        if not isinstance(context, dict):
            continue
        if context.get("manifest_id") != manifest_id:
            continue
        if context.get("account_proposal_id") == account_proposal_id:
            return context
        if fallback is None:
            fallback = context
    return fallback


def _operation_method(context: dict[str, Any], operation: str) -> dict[str, Any] | None:
    operations = context.get("operations")
    if not isinstance(operations, list):
        return None
    for item in operations:
        if not isinstance(item, dict):
            continue
        if item.get("operation") == operation:
            return item
    return None


def _field_preview(
    *,
    key: str,
    operation: str,
    method: dict[str, Any] | None,
    value: dict[str, Any] | None,
) -> dict[str, Any]:
    blockers: list[dict[str, str]] = []
    if method is None:
        blockers.append(_blocker("mapping_missing", key, "No hay metodo de edicion para este campo."))
        return {
            "standard_key": key,
            "display_name": key,
            "method": "missing",
            "status": "needs_mapping",
            "sendable": False,
            "value_present": False,
            "value_preview": "",
            "sensitive": False,
            "selector_policy": "no_selector_until_editable_capture_is_mapped",
            "blockers": blockers,
            "next_action": "Mapear el campo desde contrato o captura editable autorizada.",
        }

    method_status = _method_status_for_operation(method, operation)
    sendable = method_status in FIELD_METHOD_READY_STATUSES
    if not sendable:
        blocker_kind = "mapping_review_required" if method_status == "needs_mapping_review" else "mapping_missing"
        if method_status == "needs_editable_capture":
            blocker_kind = "editable_capture_required"
        blockers.append(_blocker(blocker_kind, key, str(method.get("next_action") or "Completar mapeo del campo.")))

    value_present = bool(value and value.get("present"))
    if sendable and method_status != "credential_secret_only" and not value_present:
        blockers.append(_blocker("local_value_missing", key, "Falta el valor local en el Hub antes de preparar escritura."))

    return {
        "standard_key": key,
        "display_name": method.get("display_name") or key,
        "method": method.get("method") or "missing",
        "status": method_status,
        "sendable": sendable and value_present,
        "value_present": value_present,
        "value_preview": value.get("preview") if value else "",
        "sensitive": bool(method.get("sensitive")),
        "selector_policy": method.get("selector_policy"),
        "observed_label_count": int((method.get("evidence_summary") or {}).get("observed_label_count") or 0),
        "editable_label_count": int((method.get("evidence_summary") or {}).get("editable_label_count") or 0),
        "mapping_count": int((method.get("evidence_summary") or {}).get("mapping_count") or 0),
        "write_path_count": int((method.get("evidence_summary") or {}).get("write_path_count") or 0),
        "approved_write_path_count": int(
            (method.get("evidence_summary") or {}).get("approved_write_path_count") or 0
        ),
        "mapping_review_statuses": list((method.get("evidence_summary") or {}).get("mapping_review_statuses") or []),
        "approved_write_path_operations": list(method.get("approved_write_path_operations") or []),
        "blockers": blockers,
        "next_action": method.get("next_action"),
    }


def _method_status_for_operation(method: dict[str, Any], operation: str) -> str:
    approved_operations = set(method.get("approved_write_path_operations") or [])
    pending_operations = set(method.get("pending_write_path_operations") or [])
    if operation in approved_operations:
        return "ready_for_preview"
    method_status = str(method.get("status") or "needs_mapping")
    if operation in pending_operations and method_status == "needs_mapping":
        return "needs_mapping_review"
    return method_status


def _blocker(kind: str, key: str, detail: str) -> dict[str, str]:
    return {
        "kind": kind,
        "standard_key": key,
        "detail": detail,
    }


def _local_values(
    *,
    company: Company | None,
    worker: Worker | None,
    version: DocumentVersion | None,
    document: Document | None,
    document_type: DocumentType | None,
) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    if company is not None:
        values.update(
            {
                "company.name": _value(company.name),
                "company.tax_id": _value(company.tax_id, sensitive=True),
                "company.address": _value(company.address),
                "company.contact_email": _value(None),
                "company.phone": _value(None),
                "company.activity_cnae": _value(None),
            }
        )
    if worker is not None:
        values.update(
            {
                "worker.first_name": _value(worker.first_name),
                "worker.last_name": _value(worker.last_name),
                "worker.identifier_value": _value(worker.identifier_value, sensitive=True, last4=worker.identifier_last4),
                "worker.nationality": _value(worker.nationality),
                "worker.social_security_number": _value(
                    worker.social_security_number,
                    sensitive=True,
                    last4=worker.social_security_last4,
                ),
                "worker.email": _value(worker.email),
                "worker.phone": _value(worker.phone, sensitive=True),
                "worker.work_position": _value(worker.work_position),
                "worker.contract_type": _value(worker.contract_type),
                "worker.starts_at": _value(worker.starts_at),
                "worker.ends_at": _value(worker.ends_at),
                "worker.medical_fitness_status": _value(worker.medical_fitness_status, sensitive=True),
                "worker.medical_fitness_expires_at": _value(worker.medical_fitness_expires_at, sensitive=True),
            }
        )
    if version is not None:
        values.update(
            {
                "document.type": _value(document_type.code if document_type else None),
                "document.file": {
                    "present": bool(version.sha256 and version.filename),
                    "preview": f"{version.filename} / sha256:{version.sha256[:8]}..." if version.sha256 else "",
                },
                "document.issued_at": _value(version.issued_at),
                "document.expires_at": _value(version.expires_at),
            }
        )
    if document is not None:
        values.setdefault("asset.type", _value(None))
        values.setdefault("asset.identifier", _value(None))
        values.setdefault("machine.code", _value(None))
        values.setdefault("machine.serial", _value(None))
        values.setdefault("vehicle.plate", _value(None))
    return values


def _value(value: object, *, sensitive: bool = False, last4: str | None = None) -> dict[str, Any]:
    present = value is not None and str(value).strip() != ""
    if not present:
        return {"present": False, "preview": ""}
    if isinstance(value, date | datetime):
        return {"present": True, "preview": value.isoformat()}
    text = str(value).strip()
    if sensitive:
        if last4:
            return {"present": True, "preview": f"***{last4}"}
        if len(text) <= 4:
            return {"present": True, "preview": "***"}
        return {"present": True, "preview": f"{text[:2]}***{text[-2:]}"}
    return {"present": True, "preview": text[:160]}


def _entity_summary(
    *,
    operation: str,
    worker: Worker | None,
    document: Document | None,
    version: DocumentVersion | None,
    document_type: DocumentType | None,
    company: Company | None,
) -> dict[str, Any]:
    if worker is not None and operation in {"upsert_worker", "deactivate_worker"}:
        return {
            "entity_type": "worker",
            "entity_id": worker.id,
            "label": f"{worker.first_name} {worker.last_name}",
        }
    if document is not None and version is not None:
        return {
            "entity_type": document.entity_type,
            "entity_id": document.entity_id,
            "document_id": document.id,
            "document_version_id": version.id,
            "document_type_code": document_type.code if document_type else None,
            "label": version.filename,
        }
    return {
        "entity_type": "company",
        "entity_id": company.id if company else None,
        "label": company.name if company else None,
    }


def _preview_status(*, preview_ready: bool, mapping_ready: bool, local_data_ready: bool) -> str:
    if preview_ready:
        return "preview_ready"
    if not mapping_ready:
        return "blocked_mapping_review_required"
    if not local_data_ready:
        return "blocked_local_data_required"
    return "blocked"


def _next_action(status: str, *, account_ready_for_live: bool) -> str:
    if status == "preview_ready":
        if not account_ready_for_live:
            return "Preview listo; activar cuenta/plataforma y registrar aprobacion antes de escritura live."
        return "Generar job de submit con aprobacion humana y auditoria antes/despues."
    if status == "blocked_local_data_required":
        return "Completar los datos locales ARM que faltan antes de preparar escritura."
    if status == "blocked_mapping_review_required":
        return "Aprobar mapeos y capturar pantalla editable autorizada antes de preparar escritura."
    return "Resolver bloqueos antes de continuar."
