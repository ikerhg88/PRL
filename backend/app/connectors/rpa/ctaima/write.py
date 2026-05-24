from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.connectors.base import ConnectorContext, ConnectorResult
from app.connectors.rpa.common_write import ConfiguredWriteConnector, WritePlatformProfile

PROJECT_ROOT = Path(__file__).resolve().parents[5]


class CtaimaWriteConnector(ConfiguredWriteConnector):
    profile = WritePlatformProfile(
        platform_slug="ctaima",
        platform_key="ctaima_cae",
        connector_key="connector_rpa_ctaima_write",
        display_name="CTAIMA / CTAIMA CAE",
    )
    connector_key = profile.connector_key
    display_name = profile.display_name
    platform_slug = profile.platform_slug
    live_helper_status = "live_implemented"
    live_helper_module_path = "app.connectors.rpa.ctaima.write"
    live_helper_script_path = "scripts/ctaima_live_upsert_worker.py"

    async def upsert_worker(
        self,
        context: ConnectorContext,
        worker_metadata: dict[str, Any],
    ) -> ConnectorResult:
        if context.dry_run or not worker_metadata.get("live_write_authorized"):
            return await super().upsert_worker(context, worker_metadata)
        return await asyncio.to_thread(self._run_live_upsert_worker, context, worker_metadata)

    def _run_live_upsert_worker(
        self,
        context: ConnectorContext,
        worker_metadata: dict[str, Any],
    ) -> ConnectorResult:
        account = dict(worker_metadata.get("account") or {})
        entry_url = str(account.get("entry_url") or "")
        account_id = str(
            account.get("source_platform_account_id")
            or account.get("platform_account_id")
            or account.get("account_proposal_id")
            or ""
        )
        if not entry_url or not account_id:
            return ConnectorResult(
                status="blocked_account_configuration_missing",
                message="CTAIMA / CTAIMA CAE: falta URL de entrada o cuenta para escritura live.",
                external_status="not_synced",
                evidence=self._base_evidence(context, operation="upsert_worker")
                | {"external_write_executed": False, "persist_external_status": False},
            )

        artifacts_dir = PROJECT_ROOT / "artifacts" / "external-writes" / "ctaima"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        worker_ref = str(worker_metadata.get("worker_ref") or "worker")
        status_file = artifacts_dir / f"upsert-worker-{_safe_token(worker_ref)}-{stamp}.status.json"
        payload_file = artifacts_dir / f"upsert-worker-{_safe_token(worker_ref)}-{stamp}.payload.tmp.json"
        payload_file.write_text(
            json.dumps(
                {
                    "worker_ref": worker_ref,
                    "identifier_type": str(worker_metadata.get("identifier_type") or ""),
                    "identifier_value": str(worker_metadata.get("identifier_value") or ""),
                    "identifier_last4": str(worker_metadata.get("identifier_last4") or ""),
                    "social_security_number": str(worker_metadata.get("social_security_number") or ""),
                    "social_security_last4": str(worker_metadata.get("social_security_last4") or ""),
                    "first_name": str(worker_metadata.get("first_name") or ""),
                    "last_name": str(worker_metadata.get("last_name") or ""),
                    "email": str(worker_metadata.get("email") or ""),
                    "phone": str(worker_metadata.get("phone") or ""),
                    "contract_type": str(worker_metadata.get("contract_type") or ""),
                    "work_position": str(worker_metadata.get("work_position") or ""),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        session_profile_dir = _session_profile_dir(
            tenant_id=context.tenant_id,
            platform_slug=self.platform_slug,
            platform_account_id=account_id,
        )
        command = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "ctaima_live_upsert_worker.py"),
            "--entry-url",
            entry_url,
            "--account-id",
            account_id,
            "--secret-ref",
            str(account.get("credential_secret_ref") or ""),
            "--platform-label",
            f"CTAIMA / {account.get('external_company_name') or account_id}",
            "--target-context",
            str(account.get("external_company_name") or ""),
            "--status-file",
            str(status_file),
            "--session-profile-dir",
            str(session_profile_dir),
            "--payload-file",
            str(payload_file),
            "--submit",
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=int(
                    worker_metadata.get("live_timeout_seconds")
                    or os.environ.get("IPRL_CAE_LIVE_HELPER_TIMEOUT_SECONDS")
                    or 1200
                ),
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ConnectorResult(
                status="live_helper_timeout",
                message=(
                    "CTAIMA / CTAIMA CAE: el helper live agoto el tiempo configurado. "
                    "No se persiste estado externo sin lectura posterior confirmada."
                ),
                external_status="not_synced",
                evidence=self._base_evidence(context, operation="upsert_worker")
                | {
                    "external_write_executed": False,
                    "post_write_read_confirmed": False,
                    "valid_external_write": False,
                    "persist_external_status": False,
                    "status_artifact": str(status_file.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                    "helper_state": "live_helper_timeout",
                    "worker_ref": worker_ref,
                    "identifier_last4": worker_metadata.get("identifier_last4"),
                    "social_security_last4": worker_metadata.get("social_security_last4"),
                    "account_proposal_id": account.get("account_proposal_id"),
                    "platform_account_id": account.get("platform_account_id"),
                },
            )
        finally:
            payload_file.unlink(missing_ok=True)

        payload = _read_status(status_file)
        stdout_payload = _parse_stdout_payload(completed.stdout)
        external_write_executed = bool(
            stdout_payload.get("external_write_executed") or payload.get("external_write_executed")
        )
        post_write_read_confirmed = bool(
            stdout_payload.get("post_write_read_confirmed") or payload.get("post_write_read_confirmed")
        )
        helper_state = str(stdout_payload.get("status") or payload.get("state") or "unknown")
        external_worker_id = stdout_payload.get("external_worker_id") or payload.get("external_worker_id")

        if completed.returncode == 0 and external_write_executed and post_write_read_confirmed:
            status = "confirmed_external"
            external_status = "confirmed"
            message = "CTAIMA / CTAIMA CAE: alta enviada y confirmada por lectura posterior."
        elif completed.returncode == 0 and post_write_read_confirmed and helper_state == "already_exists_external":
            status = "already_exists_external"
            external_status = "confirmed"
            message = "CTAIMA / CTAIMA CAE: el trabajador ya existe; alta duplicada bloqueada y lectura confirmada."
        elif completed.returncode == 0 and external_write_executed:
            status = "submitted_external_pending_readback"
            external_status = "pending_readback"
            message = "CTAIMA / CTAIMA CAE: alta enviada, pendiente de confirmacion por lectura posterior."
        else:
            status = helper_state if helper_state != "unknown" else "live_write_not_completed"
            external_status = "not_synced"
            message = f"CTAIMA / CTAIMA CAE: escritura live no completada ({status})."

        return ConnectorResult(
            status=status,
            message=message,
            external_status=external_status,
            evidence=self._base_evidence(context, operation="upsert_worker")
            | {
                "external_write_executed": external_write_executed,
                "post_write_read_confirmed": post_write_read_confirmed,
                "valid_external_write": external_write_executed and post_write_read_confirmed,
                "persist_external_status": post_write_read_confirmed,
                "status_artifact": str(status_file.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "helper_state": helper_state,
                "returncode": completed.returncode,
                "worker_ref": worker_ref,
                "external_worker_id": external_worker_id,
                "identifier_last4": worker_metadata.get("identifier_last4"),
                "social_security_last4": worker_metadata.get("social_security_last4"),
                "account_proposal_id": account.get("account_proposal_id"),
                "platform_account_id": account.get("platform_account_id"),
                "live_authorization": {
                    "manual_approval_required": context.manual_approval_required,
                    "approved_capture_evidence_required": True,
                    "captcha_bypass": False,
                    "mfa_bypass": False,
                },
            },
        )


def _read_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _parse_stdout_payload(stdout: str) -> dict[str, Any]:
    for line in reversed([item.strip() for item in stdout.splitlines() if item.strip()]):
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return {}


def _session_profile_dir(*, tenant_id: str, platform_slug: str, platform_account_id: str) -> Path:
    import hashlib

    digest = hashlib.sha256(platform_account_id.encode("utf-8")).hexdigest()[:16]
    safe_slug = _safe_token(platform_slug) or "platform"
    return PROJECT_ROOT / "storage" / "rpa-browser-profiles" / f"tenant-{_safe_token(tenant_id)}" / safe_slug / digest


def _safe_token(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_")[:80]
