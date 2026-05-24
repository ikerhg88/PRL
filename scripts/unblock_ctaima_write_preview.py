from __future__ import annotations

# ruff: noqa: E402

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("IPRL_CAE_CONFIG_FILE", str(ROOT / "config" / "iprl-cae.local.example.toml"))
os.environ.setdefault("IPRL_CAE_ENVIRONMENT", "local")
os.environ.setdefault("IPRL_CAE_DATABASE_URL", f"sqlite:///{(ROOT / 'storage' / 'demo.db').as_posix()}")
os.environ.setdefault("IPRL_CAE_DOCUMENT_STORAGE_PATH", str(ROOT / "storage" / "documents"))
os.environ.setdefault("IPRL_CAE_SECRET_KEY", "local-demo-secret-key-for-development-only-32")

from app.db.models import PlatformRpaAccountProposal, PlatformRpaManifest, PlatformWritePath
from app.db.session import get_session_factory
from app.services.platform_edit_methods import operation_required_keys
from app.services.platform_write_paths import set_write_path_review_status
from app.services.platform_write_previews import build_write_operation_preview


def main() -> None:
    parser = argparse.ArgumentParser(description="Approve evidence-backed CTAIMA worker write paths for preview.")
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--actor-user-id", type=int, default=5)
    parser.add_argument("--account-id", type=int, default=12)
    parser.add_argument("--worker-id", type=int, default=28)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "artifacts" / "platform-write-unblocks")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    with get_session_factory()() as session:
        required = set(operation_required_keys("ctaima", "upsert_worker"))
        rows = list(
            session.scalars(
                select(PlatformWritePath)
                .join(PlatformRpaManifest, PlatformRpaManifest.id == PlatformWritePath.manifest_id)
                .join(
                    PlatformRpaAccountProposal,
                    PlatformRpaAccountProposal.id == PlatformWritePath.account_proposal_id,
                )
                .where(
                    PlatformWritePath.tenant_id == args.tenant_id,
                    PlatformWritePath.account_proposal_id == args.account_id,
                    PlatformWritePath.operation == "upsert_worker",
                    PlatformRpaManifest.platform_slug == "ctaima",
                )
                .order_by(PlatformWritePath.id)
            )
        )
        reviewed: list[dict[str, Any]] = []
        approved_ids: list[int] = []
        for path in rows:
            field_keys = set(str(key) for key in (path.field_paths_json or {}))
            readback_keys = set(str(key) for key in (path.readback_paths_json or {}))
            missing = sorted(required - field_keys)
            has_identity_readback = "worker.identifier_value" in readback_keys
            has_evidence = bool(path.capture_run_id or path.source_evidence_ref)
            approvable = not missing and has_identity_readback and has_evidence
            if approvable and path.review_status != "approved":
                set_write_path_review_status(
                    session,
                    tenant_id=args.tenant_id,
                    path_id=path.id,
                    review_status="approved",
                    notes=(
                        "Approved for CTAIMA worker preview: captured Update.asp worker add form "
                        "covers required fields and worker-list readback includes identifier."
                    ),
                    actor_user_id=args.actor_user_id,
                )
                approved_ids.append(path.id)
            reviewed.append(
                {
                    "path_id": path.id,
                    "path_label": path.path_label,
                    "review_status": "approved" if approvable else path.review_status,
                    "approvable": approvable,
                    "missing_required_keys": missing,
                    "has_identity_readback": has_identity_readback,
                    "has_evidence": has_evidence,
                    "field_keys": sorted(field_keys),
                    "readback_keys": sorted(readback_keys),
                }
            )
        session.flush()
        preview = build_write_operation_preview(
            session,
            tenant_id=args.tenant_id,
            account_proposal_id=args.account_id,
            operation="upsert_worker",
            worker_id=args.worker_id,
        )
        session.commit()

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "mocks_used": False,
            "external_write_executed": False,
            "approves_only_captured_paths": True,
            "requires_identity_readback": True,
        },
        "account_proposal_id": args.account_id,
        "worker_id": args.worker_id,
        "required_keys": sorted(required),
        "approved_path_ids": approved_ids,
        "reviewed_paths": reviewed,
        "preview_status": preview["status"],
        "preview_readiness": preview["readiness"],
        "preview_blockers": preview["blockers"],
        "planned_external_changes": preview["planned_external_changes"],
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base = args.out_dir / f"ctaima_write_unblock_{stamp}"
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")
    (args.out_dir / "ctaima_write_unblock_latest.json").write_text(
        json_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (args.out_dir / "ctaima_write_unblock_latest.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), **payload["preview_readiness"]}, indent=2))


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# CTAIMA Write Unblock",
        "",
        f"- Account: `{payload['account_proposal_id']}`",
        f"- Worker: `{payload['worker_id']}`",
        f"- Approved path ids: `{payload['approved_path_ids']}`",
        f"- Preview status: `{payload['preview_status']}`",
        f"- Readiness: `{payload['preview_readiness']}`",
        "",
        "| Path | Approved | Missing keys | Identity readback |",
        "| --- | --- | --- | --- |",
    ]
    for row in payload["reviewed_paths"]:
        lines.append(
            f"| {row['path_id']} {row['path_label']} | {row['approvable']} | "
            f"{', '.join(row['missing_required_keys'])} | {row['has_identity_readback']} |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
