from __future__ import annotations

import json
import hashlib
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PlatformReviewRun, PlatformRpaAccountProposal, PlatformRpaMappingProposal
from app.db.models import Worker, WorkerPlatformRegistration
from app.services.platform_edit_methods import EDITABLE_OPERATION_REQUIRED_KEYS, operation_required_keys
from app.services.platform_mapping import extract_labels_from_capture
from app.services.platform_credentials import resolve_platform_credentials
from app.services.platform_observations import sync_readonly_capture_observations
from app.services.platform_write_paths import PlatformWritePathError, upsert_write_path_for_account
from app.services.rpa_gateway import CAPTURE_WRITE_SCREEN_ACTION

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def launch_visible_browser_for_gateway_run(
    session: Session,
    *,
    tenant_id: int,
    run_id: int,
) -> dict[str, Any] | None:
    run = session.scalar(
        select(PlatformReviewRun).where(
            PlatformReviewRun.tenant_id == tenant_id,
            PlatformReviewRun.id == run_id,
            PlatformReviewRun.trigger_source == "human_gateway_request",
        )
    )
    if run is None:
        return None
    gateway = dict((run.evidence_json or {}).get("gateway") or {})
    if not gateway.get("external_browser_authorized"):
        return {
            "run_id": run.id,
            "launched": False,
            "status": "authorization_required",
            "message": "Primero debe registrarse la autorizacion humana.",
            "pid": None,
            "credential_available": False,
            "entry_url": gateway.get("allowed_external_url"),
            "status_artifact": None,
        }
    if run.account_proposal_id is None:
        return _not_launched(run, "account_missing", "La peticion no tiene cuenta de plataforma asociada.", gateway)
    account = session.scalar(
        select(PlatformRpaAccountProposal).where(
            PlatformRpaAccountProposal.tenant_id == tenant_id,
            PlatformRpaAccountProposal.id == run.account_proposal_id,
        )
    )
    if account is None:
        return _not_launched(run, "account_missing", "No se encontro la cuenta de plataforma asociada.", gateway)
    entry_url = account.entry_url or gateway.get("allowed_external_url")
    if not entry_url:
        return _not_launched(run, "entry_url_missing", "La cuenta no tiene URL de entrada configurada.", gateway)
    if not _is_valid_http_url(entry_url):
        return _not_launched(run, "entry_url_invalid", "La cuenta tiene una URL de entrada invalida o pendiente.", gateway)

    resolution = resolve_platform_credentials(
        secret_ref=account.credential_secret_ref,
        platform_account_id=account.source_platform_account_id,
    )
    if resolution.credentials is None:
        return _not_launched(run, "credentials_missing", "No hay credenciales configuradas para esta cuenta.", gateway)

    artifacts_dir = PROJECT_ROOT / "artifacts" / "rpa-gateway" / "browser-launches"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    session_profile_dir = _session_profile_dir(
        tenant_id=tenant_id,
        platform_slug=run.platform_slug,
        platform_account_id=account.source_platform_account_id,
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    status_file = artifacts_dir / f"run-{run.id}-{stamp}.status.json"
    stdout_file = artifacts_dir / f"run-{run.id}-{stamp}.out.log"
    stderr_file = artifacts_dir / f"run-{run.id}-{stamp}.err.log"
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "assisted_platform_browser.py"),
        "--entry-url",
        entry_url,
        "--account-id",
        account.source_platform_account_id,
        "--secret-ref",
        account.credential_secret_ref or "",
        "--platform-label",
        f"{run.platform_name} / {account.external_company_name or account.source_platform_account_id}",
        "--status-file",
        str(status_file),
        "--session-profile-dir",
        str(session_profile_dir),
    ]
    target_context = account.external_company_name or gateway.get("target_context")
    if isinstance(target_context, str) and target_context.strip():
        command.extend(["--target-context", target_context.strip()])
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with stdout_file.open("w", encoding="utf-8") as stdout, stderr_file.open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=stdout,
            stderr=stderr,
            creationflags=creationflags,
        )

    launch = {
        "run_id": run.id,
        "launched": True,
        "status": "visible_browser_launched",
        "message": "Navegador visible lanzado con credenciales configuradas en memoria.",
        "pid": process.pid,
        "credential_available": True,
        "entry_url": entry_url,
        "status_artifact": str(status_file.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "session_persistence": {
            "enabled": True,
            "profile_key": session_profile_dir.name,
            "profile_reused": session_profile_dir.exists() and any(session_profile_dir.iterdir()),
            "profile_location": str(session_profile_dir.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "raw_cookies_exported": False,
        },
    }
    gateway["browser_launch"] = {
        **launch,
        "stdout_artifact": str(stdout_file.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "stderr_artifact": str(stderr_file.relative_to(PROJECT_ROOT)).replace("\\", "/"),
    }
    run.evidence_json = {**(run.evidence_json or {}), "gateway": gateway}
    session.flush()
    return launch


def read_visible_browser_status_for_gateway_run(
    session: Session,
    *,
    tenant_id: int,
    run_id: int,
) -> dict[str, Any] | None:
    run = session.scalar(
        select(PlatformReviewRun).where(
            PlatformReviewRun.tenant_id == tenant_id,
            PlatformReviewRun.id == run_id,
            PlatformReviewRun.trigger_source == "human_gateway_request",
        )
    )
    if run is None:
        return None

    gateway = dict((run.evidence_json or {}).get("gateway") or {})
    browser_launch = dict(gateway.get("browser_launch") or {})
    artifact = browser_launch.get("status_artifact")
    if not artifact:
        if browser_launch.get("launched") is False and browser_launch.get("status"):
            return {
                "run_id": run.id,
                "available": False,
                "state": str(browser_launch.get("status")),
                "message": str(browser_launch.get("message") or "El navegador guiado no se ha lanzado."),
                "updated_at_utc": browser_launch.get("updated_at_utc"),
                "platform_label": f"{run.platform_name}",
                "entry_url": gateway.get("allowed_external_url"),
            }
        return {
            "run_id": run.id,
            "available": False,
            "state": "browser_not_started",
            "message": "El navegador guiado todavia no se ha lanzado para este flujo.",
            "updated_at_utc": None,
            "platform_label": f"{run.platform_name}",
            "entry_url": gateway.get("allowed_external_url"),
        }

    allowed_dir = (PROJECT_ROOT / "artifacts" / "rpa-gateway" / "browser-launches").resolve()
    artifact_path = (PROJECT_ROOT / str(artifact)).resolve()
    try:
        artifact_path.relative_to(allowed_dir)
    except ValueError:
        return {
            "run_id": run.id,
            "available": False,
            "state": "invalid_status_artifact",
            "message": "El artefacto de estado del navegador no esta dentro del directorio permitido.",
            "updated_at_utc": None,
            "platform_label": f"{run.platform_name}",
            "entry_url": gateway.get("allowed_external_url"),
        }

    if not artifact_path.exists():
        return {
            "run_id": run.id,
            "available": False,
            "state": "status_pending",
            "message": "El navegador fue lanzado y aun no ha escrito estado.",
            "updated_at_utc": None,
            "platform_label": f"{run.platform_name}",
            "entry_url": gateway.get("allowed_external_url"),
        }

    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "run_id": run.id,
            "available": False,
            "state": "status_unreadable",
            "message": "No se pudo leer el estado redaccionado del navegador.",
            "updated_at_utc": None,
            "platform_label": f"{run.platform_name}",
            "entry_url": gateway.get("allowed_external_url"),
        }

    safe_payload = _sanitize_status_payload(payload)
    return {
        "run_id": run.id,
        "available": True,
        "state": str(safe_payload.get("state") or "unknown"),
        "message": str(safe_payload.get("message") or "Estado del navegador actualizado."),
        "updated_at_utc": safe_payload.get("updated_at_utc"),
        "platform_label": safe_payload.get("platform_label"),
        "entry_url": safe_payload.get("entry_url"),
        "selected_login_variant": safe_payload.get("selected_login_variant")
        if isinstance(safe_payload.get("selected_login_variant"), str)
        else None,
        "login_variant_policy": safe_payload.get("login_variant_policy")
        if isinstance(safe_payload.get("login_variant_policy"), dict)
        else None,
        "capture_summary": safe_payload.get("capture_summary") if isinstance(safe_payload.get("capture_summary"), dict) else None,
        "session_persistence": safe_payload.get("session_persistence")
        if isinstance(safe_payload.get("session_persistence"), dict)
        else None,
    }


def _sanitize_status_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize_status_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_status_payload(item) for item in value]
    if isinstance(value, str):
        return _safe_external_url(value)
    return value


def _safe_external_url(value: str) -> str:
    if not value:
        return value
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc and parsed.query:
        host = parsed.netloc.lower()
        params = parse_qsl(parsed.query, keep_blank_values=True)
        redact_all = host.endswith("ctaimacae.net")
        sensitive = ("token", "pass", "secret", "auth", "session", "cae")
        query_parts: list[str] = []
        changed = False
        for key, raw_val in params:
            if redact_all or any(token in key.lower() for token in sensitive):
                query_parts.append(f"{quote(key, safe='')}=[redacted]")
                changed = True
            else:
                query_parts.append(f"{quote(key, safe='')}={quote(raw_val, safe='')}")
        if changed:
            return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", "&".join(query_parts), ""))
    return re.sub(r"([?&][^=]*(?:token|pass|secret|auth|session|cae)[^=]*=)[^&]+", r"\1[redacted]", value, flags=re.I)


def sync_visible_browser_capture_for_gateway_run(
    session: Session,
    *,
    tenant_id: int,
    run_id: int,
) -> dict[str, Any] | None:
    run = session.scalar(
        select(PlatformReviewRun).where(
            PlatformReviewRun.tenant_id == tenant_id,
            PlatformReviewRun.id == run_id,
            PlatformReviewRun.trigger_source == "human_gateway_request",
        )
    )
    if run is None:
        return None

    status_payload = read_visible_browser_status_for_gateway_run(session, tenant_id=tenant_id, run_id=run_id)
    if status_payload is None:
        return None
    capture_summary = status_payload.get("capture_summary")
    if not isinstance(capture_summary, dict):
        return {
            "run_id": run.id,
            "synced": False,
            "status": "capture_not_available",
            "message": "Todavia no hay lectura de solo lectura disponible para sincronizar.",
            "pages_captured": 0,
            "status_counts": [],
            "persisted_row_level": False,
            "row_level_blocker": None,
        }

    gateway = dict((run.evidence_json or {}).get("gateway") or {})
    gateway["readonly_capture"] = capture_summary
    mapping_sync = _sync_capture_mapping_proposals(
        session,
        tenant_id=tenant_id,
        run=run,
        capture_summary=capture_summary,
    )
    gateway["readonly_capture_mapping_sync"] = mapping_sync
    write_path_sync = _sync_capture_write_paths(
        session,
        tenant_id=tenant_id,
        run=run,
        capture_summary=capture_summary,
    )
    gateway["readonly_capture_write_path_sync"] = write_path_sync
    worker_registration_sync = _sync_observed_worker_registrations(
        session,
        tenant_id=tenant_id,
        run=run,
        capture_summary=capture_summary,
    )
    gateway["readonly_capture_worker_registration_sync"] = worker_registration_sync
    observation_sync = sync_readonly_capture_observations(
        session,
        tenant_id=tenant_id,
        run=run,
        capture_summary=capture_summary,
    )
    gateway["readonly_capture_observation_sync"] = observation_sync
    run.evidence_json = {**(run.evidence_json or {}), "gateway": gateway}
    run.result_status = "readonly_capture_synced"
    run.result_summary = (
        "Lectura de plataforma sincronizada como evidencia redaccionada y estado observado del Hub; "
        "las escrituras siguen bloqueadas hasta tener mapeos aprobados."
    )
    session.flush()
    row_level_blocker = capture_summary.get("row_level_blocker")
    if isinstance(row_level_blocker, str):
        row_level_blocker = row_level_blocker.replace(
            "columnas CTAIMA",
            "campos de la plataforma",
        )
    return {
        "run_id": run.id,
        "synced": True,
        "status": "readonly_capture_synced",
        "message": run.result_summary,
        "pages_captured": int(capture_summary.get("pages_captured") or 0),
        "status_counts": capture_summary.get("status_counts") if isinstance(capture_summary.get("status_counts"), list) else [],
        "persisted_row_level": bool(capture_summary.get("persisted_row_level")),
        "row_level_blocker": row_level_blocker,
        "mapping_proposals_created": mapping_sync["created"],
        "mapping_proposals_seen": mapping_sync["seen"],
        "write_paths_upserted": write_path_sync["upserted"],
        "write_path_operations_seen": write_path_sync["operations_seen"],
        "worker_registrations_upserted": worker_registration_sync["upserted"],
        "worker_registrations_seen": worker_registration_sync["seen"],
        "observed_entities_upserted": observation_sync["entities"]["upserted"],
        "observed_document_requests_upserted": observation_sync["document_requests"]["upserted"],
    }


def _sync_capture_mapping_proposals(
    session: Session,
    *,
    tenant_id: int,
    run: PlatformReviewRun,
    capture_summary: dict[str, Any],
) -> dict[str, int]:
    labels = [
        label
        for label in extract_labels_from_capture(capture_summary)
        if label.standard_key and label.confidence >= 40
    ]
    seen = 0
    created = 0
    for label in labels:
        seen += 1
        existing = session.scalar(
            select(PlatformRpaMappingProposal).where(
                PlatformRpaMappingProposal.tenant_id == tenant_id,
                PlatformRpaMappingProposal.manifest_id == run.manifest_id,
                PlatformRpaMappingProposal.mapping_kind == "field",
                PlatformRpaMappingProposal.iker_key == label.standard_key,
                PlatformRpaMappingProposal.external_label == label.raw_label,
            )
        )
        if existing is not None:
            metadata = dict(existing.metadata_json or {})
            captures = list(metadata.get("captures") or [])
            capture_ref = {"run_id": run.id, "account_proposal_id": run.account_proposal_id}
            if capture_ref not in captures:
                captures.append(capture_ref)
            existing.metadata_json = metadata | {"captures": captures[-20:]}
            continue
        session.add(
            PlatformRpaMappingProposal(
                tenant_id=tenant_id,
                manifest_id=run.manifest_id,
                external_platform_id=run.external_platform_id,
                mapping_kind="field",
                entity_scope=label.entity_scope,
                iker_key=label.standard_key,
                external_label=label.raw_label,
                review_status="pending_review",
                status="captured_pending_mapping_review",
                metadata_json={
                    "source": "gateway_readonly_capture",
                    "run_id": run.id,
                    "account_proposal_id": run.account_proposal_id,
                    "label_kind": label.label_kind,
                    "confidence": label.confidence,
                    "page_label": label.page_label,
                    "captures": [{"run_id": run.id, "account_proposal_id": run.account_proposal_id}],
                },
                notes="Propuesta generada desde captura redaccionada; requiere revision antes de escritura live.",
            )
        )
        created += 1
    return {"seen": seen, "created": created}


def _sync_capture_write_paths(
    session: Session,
    *,
    tenant_id: int,
    run: PlatformReviewRun,
    capture_summary: dict[str, Any],
) -> dict[str, Any]:
    if run.operation != CAPTURE_WRITE_SCREEN_ACTION or run.account_proposal_id is None:
        return {"seen": 0, "upserted": 0, "operations_seen": [], "errors": []}
    editable_capture_summary = _editable_write_capture_summary(capture_summary)
    if not editable_capture_summary.get("pages"):
        return {
            "seen": 0,
            "upserted": 0,
            "operations_seen": [],
            "errors": [],
            "blocker": "no_editable_worker_page_captured",
        }
    extracted_labels = [
        label
        for label in extract_labels_from_capture(editable_capture_summary)
        if label.standard_key and label.confidence >= 40
    ]
    labels = [label for label in extracted_labels if label.label_kind == "form_field"]
    fields_by_key: dict[str, dict[str, Any]] = {}
    for label in labels:
        if label.standard_key is None:
            continue
        fields_by_key.setdefault(label.standard_key, _field_path_from_label(label))
    readback_by_key: dict[str, dict[str, Any]] = {}
    for label in extracted_labels:
        if label.standard_key is None or label.label_kind == "form_field":
            continue
        readback_by_key.setdefault(label.standard_key, _readback_path_from_label(label))

    operations_seen: list[str] = []
    errors: list[str] = []
    upserted = 0
    for operation in EDITABLE_OPERATION_REQUIRED_KEYS:
        required_keys = operation_required_keys(run.platform_slug, operation)
        field_paths = {key: fields_by_key[key] for key in required_keys if key in fields_by_key}
        if not field_paths:
            continue
        readback_paths = {key: readback_by_key[key] for key in required_keys if key in readback_by_key}
        if "worker.identifier_value" in field_paths and "worker.identifier_value" not in readback_paths:
            readback_paths["worker.identifier_value"] = {
                "strategy": "post_submit_visible_search_or_detail_readback",
                "standard_key": "worker.identifier_value",
                "source": "editable_capture_required_for_later_confirmation",
                "requires_live_confirmation": True,
            }
        operations_seen.append(operation)
        try:
            upsert_write_path_for_account(
                session,
                tenant_id=tenant_id,
                account_proposal_id=run.account_proposal_id,
                operation=operation,
                entity_scope=_operation_entity_scope(operation),
                path_kind="editable_form_capture",
                path_label=f"capture_write_screen_run_{run.id}_{operation}",
                entry_path=_entry_path_from_capture(capture_summary),
                field_paths=field_paths,
                selector_map={},
                readback_paths=readback_paths,
                capture_run_id=run.id,
                source_evidence_ref=f"platform_review_run:{run.id}",
                metadata={
                    "source": "gateway_readonly_capture",
                    "capture_run_id": run.id,
                    "auto_generated": True,
                    "approval_required": True,
                    "readback_required_before_approval": True,
                },
                actor_user_id=run.created_by,
            )
            upserted += 1
        except PlatformWritePathError as exc:
            errors.append(f"{operation}: {exc}")
    return {
        "seen": len(labels),
        "upserted": upserted,
        "operations_seen": operations_seen,
        "errors": errors[:10],
    }


def _sync_observed_worker_registrations(
    session: Session,
    *,
    tenant_id: int,
    run: PlatformReviewRun,
    capture_summary: dict[str, Any],
) -> dict[str, Any]:
    if run.account_proposal_id is None:
        return {"seen": 0, "matched": 0, "upserted": 0, "skipped": 0}
    account = session.scalar(
        select(PlatformRpaAccountProposal).where(
            PlatformRpaAccountProposal.tenant_id == tenant_id,
            PlatformRpaAccountProposal.id == run.account_proposal_id,
        )
    )
    if account is None:
        return {"seen": 0, "matched": 0, "upserted": 0, "skipped": 0}
    observed_workers = capture_summary.get("observed_workers")
    if not isinstance(observed_workers, list):
        return {"seen": 0, "matched": 0, "upserted": 0, "skipped": 0}

    seen = 0
    matched = 0
    upserted = 0
    skipped = 0
    external_platform_id = account.external_platform_id or run.external_platform_id
    for row in observed_workers:
        if not isinstance(row, dict):
            continue
        seen += 1
        worker = _match_worker_from_observed_row(session, tenant_id=tenant_id, row=row)
        if worker is None:
            skipped += 1
            continue
        matched += 1
        existing = _find_worker_platform_registration(
            session,
            tenant_id=tenant_id,
            worker_id=worker.id,
            platform_account_id=account.platform_account_id,
            external_platform_id=external_platform_id,
        )
        notes = (
            f"Alta existente confirmada por lectura de plataforma en pasarela #{run.id}. "
            "No se ha ejecutado escritura externa."
        )
        external_worker_id = row.get("external_worker_id")
        if existing is None:
            existing = WorkerPlatformRegistration(
                tenant_id=tenant_id,
                worker_id=worker.id,
                platform_account_id=account.platform_account_id,
                external_platform_id=external_platform_id,
                platform_name=run.platform_name,
                external_worker_id=str(external_worker_id) if external_worker_id else None,
                registration_status="confirmed",
                assignment_scope=account.external_company_name,
                source="rpa_readback_capture",
                last_synced_at=datetime.now(timezone.utc),
                notes=notes,
            )
            session.add(existing)
        else:
            existing.platform_account_id = existing.platform_account_id or account.platform_account_id
            existing.external_platform_id = existing.external_platform_id or external_platform_id
            if external_worker_id:
                existing.external_worker_id = str(external_worker_id)
            existing.registration_status = "confirmed"
            existing.assignment_scope = account.external_company_name or existing.assignment_scope
            existing.source = "rpa_readback_capture"
            existing.last_synced_at = datetime.now(timezone.utc)
            existing.notes = notes
        upserted += 1
    return {"seen": seen, "matched": matched, "upserted": upserted, "skipped": skipped}


def _find_worker_platform_registration(
    session: Session,
    *,
    tenant_id: int,
    worker_id: int,
    platform_account_id: int | None,
    external_platform_id: int | None,
) -> WorkerPlatformRegistration | None:
    statement = select(WorkerPlatformRegistration).where(
        WorkerPlatformRegistration.tenant_id == tenant_id,
        WorkerPlatformRegistration.worker_id == worker_id,
    )
    if platform_account_id is not None:
        account_match = session.scalar(
            statement.where(WorkerPlatformRegistration.platform_account_id == platform_account_id)
            .order_by(WorkerPlatformRegistration.id.desc())
            .limit(1)
        )
        if account_match is not None:
            return account_match
    if external_platform_id is not None:
        return session.scalar(
            statement.where(
                WorkerPlatformRegistration.external_platform_id == external_platform_id,
                WorkerPlatformRegistration.platform_account_id.is_(None),
            )
            .order_by(WorkerPlatformRegistration.id.desc())
            .limit(1)
        )
    return None


def _match_worker_from_observed_row(
    session: Session,
    *,
    tenant_id: int,
    row: dict[str, Any],
) -> Worker | None:
    identifier_last4 = str(row.get("identifier_last4") or "").strip().upper()
    display_name = str(row.get("display_name") or "").strip()
    candidates: list[Worker] = []
    if identifier_last4:
        candidates = list(
            session.scalars(
                select(Worker).where(
                    Worker.tenant_id == tenant_id,
                    Worker.identifier_last4 == identifier_last4,
                )
            )
        )
    if not candidates and display_name:
        all_workers = list(session.scalars(select(Worker).where(Worker.tenant_id == tenant_id)))
        candidates = [worker for worker in all_workers if _worker_name_matches_display(worker, display_name)]
    if len(candidates) == 1:
        return candidates[0]
    if display_name:
        named = [worker for worker in candidates if _worker_name_matches_display(worker, display_name)]
        if len(named) == 1:
            return named[0]
    return None


def _worker_name_matches_display(worker: Worker, display_name: str) -> bool:
    worker_tokens = set(_name_tokens(f"{worker.first_name} {worker.last_name}"))
    display_tokens = set(_name_tokens(display_name.replace(",", " ")))
    if not worker_tokens or not display_tokens:
        return False
    return len(worker_tokens & display_tokens) >= min(2, len(display_tokens))


def _name_tokens(value: str) -> list[str]:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return [token for token in normalized.split() if len(token) >= 3]


def _field_path_from_label(label: Any) -> dict[str, Any]:
    metadata = label.metadata or {}
    return {
        "strategy": "observed_label_or_stable_name",
        "raw_label": label.raw_label,
        "label_kind": label.label_kind,
        "page_label": label.page_label,
        "confidence": label.confidence,
        "source": metadata.get("source"),
        "tag": metadata.get("tag"),
        "input_type": metadata.get("type"),
        "required": metadata.get("required"),
        "form_index": metadata.get("form_index"),
        "field_name": metadata.get("name"),
    }


def _editable_write_capture_summary(capture_summary: dict[str, Any]) -> dict[str, Any]:
    pages = []
    for page in capture_summary.get("pages") or []:
        if not isinstance(page, dict):
            continue
        label = str(page.get("label") or "")
        if label.startswith("worker-editable:") or label.startswith("known-worker-editable:"):
            pages.append(page)
    return {**capture_summary, "pages": pages}


def _readback_path_from_label(label: Any) -> dict[str, Any]:
    metadata = label.metadata or {}
    return {
        "strategy": "observed_readback_label_or_column",
        "raw_label": label.raw_label,
        "label_kind": label.label_kind,
        "page_label": label.page_label,
        "confidence": label.confidence,
        "source": metadata.get("source"),
        "field": metadata.get("field"),
        "data_index": metadata.get("data_index"),
        "grid_index": metadata.get("grid_index"),
    }


def _entry_path_from_capture(capture_summary: dict[str, Any]) -> str | None:
    pages = capture_summary.get("pages")
    if not isinstance(pages, list):
        return None
    for page in pages:
        if not isinstance(page, dict):
            continue
        url = page.get("url")
        if isinstance(url, str) and url.strip():
            return url.strip()[:700]
    return None


def _operation_entity_scope(operation: str) -> str | None:
    if "worker" in operation:
        return "worker"
    if "company" in operation:
        return "company"
    if "machine" in operation or "vehicle" in operation:
        return "asset"
    return None


def _not_launched(run: PlatformReviewRun, status: str, message: str, gateway: dict[str, Any]) -> dict[str, Any]:
    launch = {
        "run_id": run.id,
        "launched": False,
        "status": status,
        "message": message,
        "pid": None,
        "credential_available": False,
        "entry_url": gateway.get("allowed_external_url"),
        "status_artifact": None,
        "session_persistence": None,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    gateway["browser_launch"] = launch
    run.evidence_json = {**(run.evidence_json or {}), "gateway": gateway}
    return launch


def _session_profile_dir(*, tenant_id: int, platform_slug: str, platform_account_id: str) -> Path:
    digest = hashlib.sha256(platform_account_id.encode("utf-8")).hexdigest()[:16]
    safe_slug = re.sub(r"[^a-zA-Z0-9_.-]+", "_", platform_slug).strip("_") or "platform"
    return PROJECT_ROOT / "storage" / "rpa-browser-profiles" / f"tenant-{tenant_id}" / safe_slug / digest


def _is_valid_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
