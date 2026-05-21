from __future__ import annotations

import json
import hashlib
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PlatformReviewRun, PlatformRpaAccountProposal, PlatformRpaMappingProposal
from app.services.platform_mapping import extract_labels_from_capture
from app.services.platform_credentials import resolve_platform_credentials

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
    target_context = gateway.get("target_context") or account.external_company_name
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

    return {
        "run_id": run.id,
        "available": True,
        "state": str(payload.get("state") or "unknown"),
        "message": str(payload.get("message") or "Estado del navegador actualizado."),
        "updated_at_utc": payload.get("updated_at_utc"),
        "platform_label": payload.get("platform_label"),
        "entry_url": payload.get("entry_url"),
        "selected_login_variant": payload.get("selected_login_variant")
        if isinstance(payload.get("selected_login_variant"), str)
        else None,
        "login_variant_policy": payload.get("login_variant_policy")
        if isinstance(payload.get("login_variant_policy"), dict)
        else None,
        "capture_summary": payload.get("capture_summary") if isinstance(payload.get("capture_summary"), dict) else None,
        "session_persistence": payload.get("session_persistence")
        if isinstance(payload.get("session_persistence"), dict)
        else None,
    }


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
    run.evidence_json = {**(run.evidence_json or {}), "gateway": gateway}
    run.result_status = "readonly_capture_synced"
    run.result_summary = (
        "Lectura de plataforma sincronizada como evidencia redaccionada del Hub; "
        "faltan mapeos aprobados para persistir filas por trabajador/documento."
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
