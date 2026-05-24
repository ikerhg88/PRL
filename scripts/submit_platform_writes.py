from __future__ import annotations

# ruff: noqa: E402

import argparse
import asyncio
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("IPRL_CAE_CONFIG_FILE", str(ROOT / "config" / "iprl-cae.local.example.toml"))
os.environ.setdefault("IPRL_CAE_ENVIRONMENT", "local")
os.environ.setdefault("IPRL_CAE_DATABASE_URL", f"sqlite:///{(ROOT / 'storage' / 'demo.db').as_posix()}")
os.environ.setdefault("IPRL_CAE_DOCUMENT_STORAGE_PATH", str(ROOT / "storage" / "documents"))
os.environ.setdefault("IPRL_CAE_SECRET_KEY", "local-demo-secret-key-for-development-only-32")

from app.api.exchange import submit_mass_platform_updates
from app.db.session import get_session_factory
from app.schemas import ExchangeMassUpdateSubmitRequest


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit Hub-approved platform write actions and save the result.")
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--actor-user-id", type=int, default=5)
    parser.add_argument("--company-id", type=int, default=None)
    parser.add_argument("--worker-id", action="append", type=int, default=[])
    parser.add_argument("--platform-slug", action="append", default=[])
    parser.add_argument("--account-id", action="append", type=int, default=[])
    parser.add_argument("--action-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--include-missing-workers", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-document-requests", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--only-active-contexts", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--create-capture-requests", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--live", action="store_true", help="Request live external writes with explicit authorization.")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "artifacts" / "platform-write-submits")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    request = ExchangeMassUpdateSubmitRequest(
        company_id=args.company_id,
        platform_slugs=[slug for slug in args.platform_slug if slug],
        account_proposal_ids=args.account_id,
        worker_ids=args.worker_id,
        include_missing_workers=args.include_missing_workers,
        include_document_requests=args.include_document_requests,
        only_active_contexts=args.only_active_contexts,
        limit=args.limit,
        action_ids=[action_id for action_id in args.action_id if action_id],
        dry_run=not args.live,
        manual_approval_required=True,
        live_external_write_authorized=bool(args.live),
        create_capture_requests=args.create_capture_requests,
    )

    with get_session_factory()() as session:
        payload = asyncio.run(
            submit_mass_platform_updates(
                request,
                tenant_id=args.tenant_id,
                session=session,
                actor_user_id=args.actor_user_id,
            )
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base = args.out_dir / f"platform_write_submit_{stamp}"
    json_path = base.with_suffix(".json")
    csv_path = base.with_suffix(".csv")
    md_path = base.with_suffix(".md")
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    _write_csv(csv_path, payload.get("rows") or [])
    md_path.write_text(_markdown(payload, request=request), encoding="utf-8")
    (args.out_dir / "platform_write_submit_latest.json").write_text(
        json_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (args.out_dir / "platform_write_submit_latest.csv").write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")
    (args.out_dir / "platform_write_submit_latest.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps(payload.get("summary", {}) | {"json": str(json_path), "markdown": str(md_path)}, indent=2))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _markdown(payload: dict[str, Any], *, request: ExchangeMassUpdateSubmitRequest) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# Platform write submit",
        "",
        f"- Dry run: `{request.dry_run}`",
        f"- Live external write authorized: `{request.live_external_write_authorized}`",
        f"- Summary: `{summary}`",
        "",
        "| Platform | Account | Operation | Preview | Status | Transfer | Detail |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload.get("rows") or []:
        lines.append(
            "| "
            f"{row.get('platform_name') or row.get('platform_slug') or ''} | "
            f"{row.get('external_company_name') or ''} | "
            f"{row.get('operation') or ''} | "
            f"{row.get('preview_status') or ''} | "
            f"{row.get('status') or ''} | "
            f"{row.get('transfer_id') or ''} | "
            f"{str(row.get('detail') or '')[:220]} |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
