from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    PlatformReviewRun,
    PlatformReviewSchedule,
    PlatformRpaAccountProposal,
    PlatformRpaManifest,
    Worker,
    WorkerPlatformRegistration,
)
from app.services.platform_review_runs import run_to_read
from app.services.platform_review_schedules import DEFAULT_INTERVAL_MINUTES, DEFAULT_REVIEW_SCOPE

READ_STATUS_ACTION = "read_external_status"
CAPTURE_WRITE_SCREEN_ACTION = "capture_write_screen"
GATEWAY_TRIGGER_SOURCE = "human_gateway_request"

GATEWAY_ACTIONS = [
    {
        "action_key": READ_STATUS_ACTION,
        "label": "Revisar estado",
        "description": "Abrir una revision asistida de estado documental en solo lectura.",
        "enabled": True,
        "writes_external_system": False,
    },
    {
        "action_key": CAPTURE_WRITE_SCREEN_ACTION,
        "label": "Mapear pantalla editable",
        "description": "Abrir la plataforma para capturar estructura editable redaccionada sin guardar cambios.",
        "enabled": True,
        "writes_external_system": False,
    },
    {
        "action_key": "upload_worker_document",
        "label": "Subir documento de trabajador",
        "description": "Escritura externa automatizada: requiere preview, fichero, mapeo aprobado y aprobacion.",
        "enabled": False,
        "writes_external_system": True,
    },
    {
        "action_key": "upload_company_document",
        "label": "Subir documento de empresa",
        "description": "Escritura externa automatizada: requiere preview, fichero, mapeo aprobado y aprobacion.",
        "enabled": False,
        "writes_external_system": True,
    },
]

DECISION_SUMMARIES = {
    "authorize_enter_page": "Operador autorizo abrir navegador visible para resolver control humano.",
    "human_control_resolved": "Operador marco el control humano como resuelto.",
    "cancel": "Operador cancelo la peticion asistida.",
}


def gateway_options(
    session: Session,
    *,
    tenant_id: int,
    priority_group: str | None = None,
) -> dict[str, Any]:
    schedules = _gateway_schedules(session, tenant_id=tenant_id, priority_group=priority_group)
    return {
        "actions": GATEWAY_ACTIONS,
        "schedules": [_schedule_option(schedule, manifest) for schedule, manifest in schedules],
        "policy": {
            "captcha_bypass_supported": False,
            "mfa_bypass_supported": False,
            "proxy_rotation_supported": False,
            "visible_browser_required_for_human_controls": True,
            "external_writes_enabled": False,
            "fixed_actions_only": True,
        },
    }


def list_gateway_requests(
    session: Session,
    *,
    tenant_id: int,
    limit: int = 50,
) -> list[dict[str, Any]]:
    runs = session.scalars(
        select(PlatformReviewRun)
        .where(
            PlatformReviewRun.tenant_id == tenant_id,
            PlatformReviewRun.trigger_source == GATEWAY_TRIGGER_SOURCE,
        )
        .order_by(PlatformReviewRun.id.desc())
        .limit(limit)
    )
    return [run_to_read(run) for run in runs]


def create_gateway_request(
    session: Session,
    *,
    tenant_id: int,
    schedule_id: int | None = None,
    manifest_id: int | None = None,
    account_proposal_id: int | None = None,
    action_key: str,
    actor_user_id: int | None,
    request_comment: str | None = None,
) -> PlatformReviewRun | None:
    if action_key not in {READ_STATUS_ACTION, CAPTURE_WRITE_SCREEN_ACTION}:
        raise ValueError("Solo estan habilitadas las acciones seguras de lectura o mapeo editable.")

    resolved = _resolve_or_create_gateway_schedule(
        session,
        tenant_id=tenant_id,
        schedule_id=schedule_id,
        manifest_id=manifest_id,
        actor_user_id=actor_user_id,
    )
    if resolved is None:
        return None
    schedule, manifest = resolved
    account = _resolve_account(
        session,
        tenant_id=tenant_id,
        manifest_id=manifest.id,
        account_proposal_id=account_proposal_id,
    )
    now = datetime.now(timezone.utc)
    run = PlatformReviewRun(
        tenant_id=tenant_id,
        schedule_id=schedule.id,
        manifest_id=manifest.id,
        account_proposal_id=account.id if account is not None else None,
        external_platform_id=manifest.external_platform_id,
        platform_slug=manifest.platform_slug,
        platform_name=manifest.platform_name,
        operation=action_key,
        trigger_source=GATEWAY_TRIGGER_SOURCE,
        status="human_action_required",
        dry_run=True,
        manual_approval_required=True,
        started_at=now,
        result_status="waiting_human_gateway",
        result_summary="Peticion creada en pasarela humana; pendiente de autorizacion del operador.",
        created_by=actor_user_id,
        evidence_json=_initial_gateway_evidence(
            session=session,
            tenant_id=tenant_id,
            manifest=manifest,
            account=account,
            actor_user_id=actor_user_id,
            request_comment=request_comment,
            action_key=action_key,
            created_at=now,
        ),
    )
    session.add(run)
    session.flush()
    return run


def apply_gateway_decision(
    session: Session,
    *,
    tenant_id: int,
    run_id: int,
    decision: str,
    actor_user_id: int | None,
    notes: str | None = None,
) -> PlatformReviewRun | None:
    run = session.scalar(
        select(PlatformReviewRun).where(
            PlatformReviewRun.tenant_id == tenant_id,
            PlatformReviewRun.id == run_id,
            PlatformReviewRun.trigger_source == GATEWAY_TRIGGER_SOURCE,
        )
    )
    if run is None:
        return None
    if decision not in DECISION_SUMMARIES:
        raise ValueError("Decision de pasarela no soportada.")

    now = datetime.now(timezone.utc)
    gateway = dict(run.evidence_json.get("gateway") or {})
    audit_log = list(gateway.get("audit_log") or [])
    audit_log.append(
        {
            "at": now.isoformat(),
            "actor_user_id": actor_user_id,
            "event": decision,
            "notes": _redact_gateway_text(notes or ""),
        }
    )
    gateway["audit_log"] = audit_log
    gateway["last_human_decision"] = decision
    gateway["last_human_decision_at"] = now.isoformat()
    gateway["last_human_notes"] = _redact_gateway_text(notes or "")

    if decision == "authorize_enter_page":
        run.status = "human_action_required"
        run.result_status = "human_gate_authorized"
        run.result_summary = DECISION_SUMMARIES[decision]
        gateway["external_browser_authorized"] = True
        gateway["next_step"] = "El operador resuelve captcha/MFA/aviso en navegador visible."
    elif decision == "human_control_resolved":
        run.status = "completed_with_warnings"
        run.result_status = "human_control_resolved"
        run.result_summary = (
            "Control humano marcado como resuelto; no se ejecuto ninguna escritura externa."
        )
        run.finished_at = now
        gateway["external_browser_authorized"] = True
        gateway["changes_applied"] = []
        gateway["next_step"] = "Revisar evidencias y lanzar lectura automatizada si el conector lo permite."
    else:
        run.status = "cancelled"
        run.result_status = "human_cancelled"
        run.result_summary = DECISION_SUMMARIES[decision]
        run.finished_at = now
        gateway["next_step"] = "Peticion cerrada sin acceder o continuar en plataforma externa."

    run.evidence_json = {**(run.evidence_json or {}), "gateway": gateway}
    session.flush()
    return run


def _gateway_schedules(
    session: Session,
    *,
    tenant_id: int,
    priority_group: str | None,
) -> list[tuple[PlatformReviewSchedule, PlatformRpaManifest]]:
    statement = (
        select(PlatformReviewSchedule, PlatformRpaManifest)
        .join(PlatformRpaManifest, PlatformRpaManifest.id == PlatformReviewSchedule.manifest_id)
        .where(PlatformReviewSchedule.tenant_id == tenant_id)
    )
    if priority_group is not None:
        statement = statement.where(PlatformRpaManifest.priority_group == priority_group)
    return [(schedule, manifest) for schedule, manifest in session.execute(statement.order_by(PlatformRpaManifest.platform_name)).all()]


def _resolve_or_create_gateway_schedule(
    session: Session,
    *,
    tenant_id: int,
    schedule_id: int | None,
    manifest_id: int | None,
    actor_user_id: int | None,
) -> tuple[PlatformReviewSchedule, PlatformRpaManifest] | None:
    if schedule_id is not None:
        schedule = session.scalar(
            select(PlatformReviewSchedule).where(
                PlatformReviewSchedule.tenant_id == tenant_id,
                PlatformReviewSchedule.id == schedule_id,
            )
        )
        if schedule is None:
            return None
        manifest = session.get(PlatformRpaManifest, schedule.manifest_id)
        if manifest is None or manifest.tenant_id != tenant_id:
            return None
        return schedule, manifest

    if manifest_id is None:
        return None
    manifest = session.scalar(
        select(PlatformRpaManifest).where(
            PlatformRpaManifest.tenant_id == tenant_id,
            PlatformRpaManifest.id == manifest_id,
        )
    )
    if manifest is None:
        return None
    schedule = session.scalar(
        select(PlatformReviewSchedule).where(
            PlatformReviewSchedule.tenant_id == tenant_id,
            PlatformReviewSchedule.manifest_id == manifest.id,
        )
    )
    if schedule is None:
        schedule = PlatformReviewSchedule(
            tenant_id=tenant_id,
            manifest_id=manifest.id,
            external_platform_id=manifest.external_platform_id,
            enabled=False,
            interval_minutes=DEFAULT_INTERVAL_MINUTES,
            review_scope=list(DEFAULT_REVIEW_SCOPE),
            status="disabled",
            dry_run=True,
            manual_approval_required=True,
            notes="Controlador creado desde pasarela humana; recarga externa pendiente de autorizacion.",
            created_by=actor_user_id,
        )
        session.add(schedule)
        session.flush()
    return schedule, manifest


def _schedule_option(schedule: PlatformReviewSchedule, manifest: PlatformRpaManifest) -> dict[str, Any]:
    return {
        "schedule_id": schedule.id,
        "manifest_id": manifest.id,
        "platform_slug": manifest.platform_slug,
        "platform_name": manifest.platform_name,
        "enabled": schedule.enabled,
        "dry_run": schedule.dry_run,
        "manual_approval_required": schedule.manual_approval_required,
        "last_result_status": schedule.last_result_status,
        "next_run_at": schedule.next_run_at,
        "human_assisted_supported": bool(manifest.rpa_assisted_on_control),
    }


def _resolve_account(
    session: Session,
    *,
    tenant_id: int,
    manifest_id: int,
    account_proposal_id: int | None,
) -> PlatformRpaAccountProposal | None:
    statement = select(PlatformRpaAccountProposal).where(
        PlatformRpaAccountProposal.tenant_id == tenant_id,
        PlatformRpaAccountProposal.manifest_id == manifest_id,
    )
    if account_proposal_id is not None:
        return session.scalar(statement.where(PlatformRpaAccountProposal.id == account_proposal_id))

    accounts = list(session.scalars(statement.order_by(PlatformRpaAccountProposal.id)))
    manifest = session.get(PlatformRpaManifest, manifest_id)
    if manifest is not None and manifest.platform_slug == "ctaima":
        sofidel = next(
            (
                account
                for account in accounts
                if account.external_company_name and "SOFIDEL" in account.external_company_name.upper()
            ),
            None,
        )
        if sofidel is not None:
            return sofidel
    return accounts[0] if accounts else None


def _first_account(
    session: Session,
    *,
    tenant_id: int,
    manifest_id: int,
) -> PlatformRpaAccountProposal | None:
    return _resolve_account(
        session,
        tenant_id=tenant_id,
        manifest_id=manifest_id,
        account_proposal_id=None,
    )


def _initial_gateway_evidence(
    *,
    session: Session,
    tenant_id: int,
    manifest: PlatformRpaManifest,
    account: PlatformRpaAccountProposal | None,
    actor_user_id: int | None,
    request_comment: str | None,
    action_key: str,
    created_at: datetime,
) -> dict[str, Any]:
    target_context = _target_context(
        session,
        tenant_id=tenant_id,
        manifest=manifest,
        account=account,
    )
    return {
        "gateway": {
            "mode": "human_assisted_gateway",
            "ui_boundary": "Pantalla propia del Hub; no replica la web original del proveedor.",
            "requested_action": action_key,
            "requested_action_label": _action_label(action_key),
            "request_comment": _redact_gateway_text(request_comment or ""),
            "fixed_actions_only": True,
            "external_browser_authorized": False,
            "visible_browser_required": True,
            "writes_external_system": False,
            "planned_external_changes": [],
            "changes_applied": [],
            "human_required_reason": "captcha_mfa_notice_or_manual_company_selection_possible",
            "allowed_external_host": _host(account.entry_url if account is not None else None),
            "allowed_external_url": account.entry_url if account is not None else None,
            "external_account": account.source_platform_account_id if account is not None else None,
            "external_company_name": account.external_company_name if account is not None else None,
            "target_context": target_context,
            "guided_flow": _guided_flow(
                session,
                tenant_id=tenant_id,
                manifest=manifest,
                account=account,
                action_key=action_key,
            ),
            "platform_slug": manifest.platform_slug,
            "platform_name": manifest.platform_name,
            "safe_controls": {
                "dry_run": True,
                "manual_approval_required": True,
                "captcha_bypass": False,
                "mfa_bypass": False,
                "proxy_rotation": False,
            },
            "operator_steps": [
                "Revisar el plan y el alcance dentro del Hub.",
                "Autorizar entrada solo si la cuenta y plataforma son correctas.",
                "Resolver captcha, MFA o aviso legal manualmente en navegador visible.",
                "No guardar cambios ni subir ficheros durante lectura o mapeo de pantalla.",
                "Volver al Hub y registrar el resultado humano.",
            ],
            "audit_log": [
                {
                    "at": created_at.isoformat(),
                    "actor_user_id": actor_user_id,
                    "event": "request_created",
                    "notes": "Peticion de revision asistida creada.",
                }
            ],
        }
    }


def _target_context(
    session: Session,
    *,
    tenant_id: int,
    manifest: PlatformRpaManifest,
    account: PlatformRpaAccountProposal | None,
) -> str | None:
    pending = _first_pending_registration(session, tenant_id=tenant_id, manifest=manifest, account=account)
    if pending is not None:
        _worker, registration = pending
        if registration.assignment_scope:
            return registration.assignment_scope
    return account.external_company_name if account is not None else None


def _guided_flow(
    session: Session,
    *,
    tenant_id: int,
    manifest: PlatformRpaManifest,
    account: PlatformRpaAccountProposal | None,
    action_key: str,
) -> dict[str, Any]:
    pending = _first_pending_registration(session, tenant_id=tenant_id, manifest=manifest, account=account)
    target_summary = "Revisar estados documentales externos de la cuenta seleccionada sin modificar datos."
    boundary = "Solo lectura: no subir documentos, no guardar cambios y no enviar formularios de escritura."
    if action_key == CAPTURE_WRITE_SCREEN_ACTION:
        target_summary = (
            "Abrir una pantalla de edicion autorizada para capturar etiquetas, campos y botones sin guardar cambios."
        )
        boundary = "Mapeo editable: se puede abrir el formulario, pero no se pulsa Guardar ni se suben ficheros."
    target_detail = None
    if pending is not None:
        worker, registration = pending
        worker_name = f"{worker.first_name} {worker.last_name}".strip()
        scope = f"{registration.assignment_scope}: " if registration.assignment_scope else ""
        target_summary = (
            f"Verificar {scope}{worker_name} en {manifest.platform_name}; "
            f"estado local pendiente: {registration.registration_status}."
        )
        target_detail = registration.notes

    return {
        "title": f"Flujo guiado de lectura para {manifest.platform_name}",
        "objective": target_summary,
        "target_detail": target_detail,
        "account_context": account.external_company_name if account is not None else None,
        "read_only_boundary": boundary,
        "steps": [
            "Preparar peticion y alcance dentro del Hub.",
            "Resolver credenciales desde configuracion segura sin mostrarlas al operador.",
            "Abrir navegador visible de la plataforma seleccionada.",
            "Si aparece captcha/MFA/aviso, el humano lo resuelve en pantalla.",
            "El asistente introduce credenciales cuando localiza el formulario permitido.",
            "El operador verifica la pantalla objetivo y vuelve al Hub para sincronizar la captura redaccionada.",
        ],
        "cannot_automate": [
            "No se resuelve captcha/MFA automaticamente.",
            "No se inventan selectores ni rutas internas de la plataforma.",
            "No se ejecutan escrituras externas durante esta captura.",
        ],
    }


def _action_label(action_key: str) -> str:
    if action_key == CAPTURE_WRITE_SCREEN_ACTION:
        return "Mapear pantalla editable"
    return "Revisar estado"


def _first_pending_registration(
    session: Session,
    *,
    tenant_id: int,
    manifest: PlatformRpaManifest,
    account: PlatformRpaAccountProposal | None,
) -> tuple[Worker, WorkerPlatformRegistration] | None:
    rows = session.execute(
        select(Worker, WorkerPlatformRegistration)
        .join(WorkerPlatformRegistration, WorkerPlatformRegistration.worker_id == Worker.id)
        .where(
            Worker.tenant_id == tenant_id,
            WorkerPlatformRegistration.tenant_id == tenant_id,
        )
        .order_by(WorkerPlatformRegistration.id)
    ).all()
    manifest_tokens = {
        _normalize_platform_token(manifest.platform_slug),
        _normalize_platform_token(manifest.platform_name),
    }
    account_scope = (account.external_company_name or "").upper() if account is not None else ""
    account_platform_id = account.platform_account_id if account is not None else None
    candidates: list[tuple[int, Worker, WorkerPlatformRegistration]] = []
    for worker, registration in rows:
        if account_platform_id is not None and registration.platform_account_id not in {None, account_platform_id}:
            continue
        registration_token = _normalize_platform_token(registration.platform_name)
        if not any(
            token and (registration_token == token or token in registration_token or registration_token in token)
            for token in manifest_tokens
        ):
            continue
        if account_scope and registration.assignment_scope and not _scope_matches_account(
            registration.assignment_scope,
            account_scope,
        ):
            continue
        if account_scope and registration.assignment_scope is None and registration.platform_account_id is None:
            continue
        if registration.registration_status in {"registered", "valid", "valid_external", "synced", "active"}:
            continue
        score = 0
        if account_scope and registration.assignment_scope and _scope_matches_account(
            registration.assignment_scope,
            account_scope,
        ):
            score += 10
        if account_platform_id is not None and registration.platform_account_id == account_platform_id:
            score += 20
        if registration.registration_status == "missing_required_document":
            score += 5
        candidates.append((score, worker, registration))
    if not candidates:
        return None
    _, worker, registration = sorted(candidates, key=lambda item: (-item[0], item[2].id))[0]
    return worker, registration


def _host(entry_url: str | None) -> str | None:
    if not entry_url:
        return None
    return urlparse(entry_url).netloc or None


def _normalize_platform_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _scope_matches_account(registration_scope: str, account_scope: str) -> bool:
    registration_normalized = _normalize_scope_text(registration_scope)
    account_normalized = _normalize_scope_text(account_scope)
    if not registration_normalized or not account_normalized:
        return False
    if registration_normalized in account_normalized or account_normalized in registration_normalized:
        return True
    return bool(_scope_tokens(registration_normalized) & _scope_tokens(account_normalized))


def _normalize_scope_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _scope_tokens(value: str) -> set[str]:
    stopwords = {
        "arm",
        "industrial",
        "assemblies",
        "assembly",
        "grupo",
        "group",
        "empresa",
        "company",
        "centro",
        "trabajo",
    }
    return {token for token in value.split() if len(token) >= 4 and token not in stopwords}


def _redact_gateway_text(value: str) -> str:
    text = re.sub(r"[\w.\-+]+@[\w.\-]+\.\w+", "[email]", value)
    text = re.sub(r"\b\d{8}[A-Za-z]\b", "[dni]", text)
    text = re.sub(r"\b[XYZ]\d{7}[A-Za-z]\b", "[nie]", text, flags=re.I)
    text = re.sub(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b", "[phone-or-id]", text)
    return " ".join(text.split())[:500]
