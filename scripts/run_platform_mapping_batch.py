from __future__ import annotations

# ruff: noqa: E402

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("IPRL_CAE_CONFIG_FILE", str(ROOT / "config" / "iprl-cae.local.example.toml"))
os.environ.setdefault("IPRL_CAE_ENVIRONMENT", "local")
os.environ.setdefault("IPRL_CAE_DATABASE_URL", f"sqlite:///{(ROOT / 'storage' / 'demo.db').as_posix()}")
os.environ.setdefault("IPRL_CAE_DOCUMENT_STORAGE_PATH", str(ROOT / "storage" / "documents"))
os.environ.setdefault("IPRL_CAE_SECRET_KEY", "local-demo-secret-key-for-development-only-32")

from sqlalchemy import select

from app.db.models import PlatformReviewRun, PlatformRpaAccountProposal, PlatformRpaManifest
from app.db.session import get_session_factory
from app.services.rpa_assisted_browser import (
    launch_visible_browser_for_gateway_run,
    read_visible_browser_status_for_gateway_run,
    sync_visible_browser_capture_for_gateway_run,
)
from app.services.rpa_gateway import CAPTURE_WRITE_SCREEN_ACTION, apply_gateway_decision, create_gateway_request


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run safe visible Playwright mapping across CAE platform accounts without external writes."
    )
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--actor-user-id", type=int, default=1)
    parser.add_argument("--account-id", action="append", type=int, default=[])
    parser.add_argument("--platform-slug", action="append", default=[])
    parser.add_argument("--statuses", nargs="*", default=["active", "proposal_disabled"])
    parser.add_argument("--one-per-platform", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--wait-seconds", type=int, default=45)
    parser.add_argument("--poll-seconds", type=int, default=5)
    parser.add_argument("--browser-channel", choices=("auto", "chromium", "chrome", "msedge"), default="auto")
    parser.add_argument("--launch", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--sync", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--close-after", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--max-accounts", type=int, default=0)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "artifacts" / "platform-mapping-batch")
    args = parser.parse_args()

    if args.browser_channel != "auto":
        os.environ["IPRL_CAE_BROWSER_CHANNEL"] = args.browser_channel
    args.out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    with get_session_factory()() as session:
        targets = _select_targets(
            session,
            tenant_id=args.tenant_id,
            account_ids=set(args.account_id),
            platform_slugs={slug for slug in args.platform_slug if slug},
            statuses=set(args.statuses),
            one_per_platform=args.one_per_platform,
            max_accounts=args.max_accounts,
        )
        for account, manifest in targets:
            row = _run_target(
                session,
                tenant_id=args.tenant_id,
                actor_user_id=args.actor_user_id,
                account=account,
                manifest=manifest,
                launch=args.launch,
                sync=args.sync,
                wait_seconds=args.wait_seconds,
                poll_seconds=args.poll_seconds,
                close_after=args.close_after,
                browser_channel=args.browser_channel,
            )
            rows.append(row)
            session.commit()

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "external_write_executed": False,
            "captcha_bypass": False,
            "mfa_bypass": False,
            "opaque_token_calculation": False,
            "browser_channel": args.browser_channel,
            "visible_playwright": args.launch,
        },
        "summary": _summary(rows),
        "rows": rows,
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base = args.out_dir / f"platform_mapping_batch_{stamp}"
    json_path = base.with_suffix(".json")
    csv_path = base.with_suffix(".csv")
    xlsx_path = base.with_suffix(".xlsx")
    md_path = base.with_suffix(".md")
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    _write_csv(csv_path, rows)
    _write_xlsx(xlsx_path, rows)
    md_path.write_text(_markdown(payload), encoding="utf-8")
    (args.out_dir / "platform_mapping_batch_latest.json").write_text(
        json_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (args.out_dir / "platform_mapping_batch_latest.csv").write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")
    (args.out_dir / "platform_mapping_batch_latest.xlsx").write_bytes(xlsx_path.read_bytes())
    (args.out_dir / "platform_mapping_batch_latest.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(
        json.dumps(
            payload["summary"] | {"json": str(json_path), "xlsx": str(xlsx_path), "markdown": str(md_path)},
            ensure_ascii=False,
            indent=2,
        )
    )


def _select_targets(
    session,
    *,
    tenant_id: int,
    account_ids: set[int],
    platform_slugs: set[str],
    statuses: set[str],
    one_per_platform: bool,
    max_accounts: int,
) -> list[tuple[PlatformRpaAccountProposal, PlatformRpaManifest]]:
    manifests = {
        manifest.id: manifest
        for manifest in session.scalars(
            select(PlatformRpaManifest).where(PlatformRpaManifest.tenant_id == tenant_id)
        )
    }
    statement = select(PlatformRpaAccountProposal).where(PlatformRpaAccountProposal.tenant_id == tenant_id)
    if account_ids:
        statement = statement.where(PlatformRpaAccountProposal.id.in_(account_ids))
    elif statuses:
        statement = statement.where(PlatformRpaAccountProposal.status.in_(statuses))
    accounts = list(session.scalars(statement.order_by(PlatformRpaAccountProposal.id)))
    targets: list[tuple[PlatformRpaAccountProposal, PlatformRpaManifest]] = []
    seen_platforms: set[str] = set()
    for account in accounts:
        manifest = manifests.get(account.manifest_id)
        if manifest is None:
            continue
        if platform_slugs and manifest.platform_slug not in platform_slugs:
            continue
        if not account.entry_url or not account.credential_secret_ref:
            continue
        if one_per_platform and manifest.platform_slug in seen_platforms:
            continue
        targets.append((account, manifest))
        seen_platforms.add(manifest.platform_slug)
        if max_accounts and len(targets) >= max_accounts:
            break
    return targets


def _run_target(
    session,
    *,
    tenant_id: int,
    actor_user_id: int,
    account: PlatformRpaAccountProposal,
    manifest: PlatformRpaManifest,
    launch: bool,
    sync: bool,
    wait_seconds: int,
    poll_seconds: int,
    close_after: bool,
    browser_channel: str,
) -> dict[str, Any]:
    run = _latest_capture_run(session, tenant_id=tenant_id, account_id=account.id)
    created = False
    if run is None:
        run = create_gateway_request(
            session,
            tenant_id=tenant_id,
            manifest_id=manifest.id,
            account_proposal_id=account.id,
            action_key=CAPTURE_WRITE_SCREEN_ACTION,
            actor_user_id=actor_user_id,
            request_comment="Batch Playwright assisted platform mapping; no external writes.",
        )
        created = True
    gateway = dict((run.evidence_json or {}).get("gateway") or {})
    authorized = bool(gateway.get("external_browser_authorized"))
    if not authorized:
        run = apply_gateway_decision(
            session,
            tenant_id=tenant_id,
            run_id=run.id,
            decision="authorize_enter_page",
            actor_user_id=actor_user_id,
            notes="Authorized visible Playwright mapping only; no external writes.",
        )
        authorized = True

    launch_payload = None
    pid = None
    if launch:
        launch_payload = launch_visible_browser_for_gateway_run(session, tenant_id=tenant_id, run_id=run.id)
        pid = (launch_payload or {}).get("pid")
        session.flush()

    status_payload = None
    capture_seen = False
    deadline = time.monotonic() + max(wait_seconds, 1)
    while time.monotonic() < deadline:
        status_payload = read_visible_browser_status_for_gateway_run(session, tenant_id=tenant_id, run_id=run.id)
        capture_seen = isinstance((status_payload or {}).get("capture_summary"), dict)
        if capture_seen:
            break
        state = str((status_payload or {}).get("state") or "")
        if state in {"credentials_missing", "browser_launch_failed", "managed_browser_missing", "browser_closed"}:
            break
        time.sleep(max(poll_seconds, 1))

    sync_payload = None
    if sync and capture_seen:
        sync_payload = sync_visible_browser_capture_for_gateway_run(session, tenant_id=tenant_id, run_id=run.id)

    if close_after and pid:
        _kill_process_tree(int(pid))

    capture_summary = (status_payload or {}).get("capture_summary") if isinstance(status_payload, dict) else None
    page_routes = _page_routes(capture_summary)
    editable_field_names = _editable_field_names(capture_summary)
    return {
        "account_proposal_id": account.id,
        "platform_slug": manifest.platform_slug,
        "platform_name": manifest.platform_name,
        "external_company_name": account.external_company_name,
        "account_status": account.status,
        "run_id": run.id,
        "created": created,
        "authorized": authorized,
        "browser_channel": browser_channel,
        "launch_status": (launch_payload or {}).get("status"),
        "pid": pid,
        "status_state": (status_payload or {}).get("state") if isinstance(status_payload, dict) else None,
        "entry_url": (status_payload or {}).get("entry_url") if isinstance(status_payload, dict) else None,
        "capture_available": bool(capture_seen),
        "pages_captured": int((capture_summary or {}).get("pages_captured") or 0) if isinstance(capture_summary, dict) else 0,
        "page_routes": page_routes,
        "editable_field_names": editable_field_names,
        "observed_workers": len((capture_summary or {}).get("observed_workers") or []) if isinstance(capture_summary, dict) else 0,
        "sync_status": (sync_payload or {}).get("status") if isinstance(sync_payload, dict) else None,
        "mapping_proposals_created": int((sync_payload or {}).get("mapping_proposals_created") or 0)
        if isinstance(sync_payload, dict)
        else 0,
        "write_paths_upserted": int((sync_payload or {}).get("write_paths_upserted") or 0)
        if isinstance(sync_payload, dict)
        else 0,
        "write_path_operations_seen": (sync_payload or {}).get("write_path_operations_seen") if isinstance(sync_payload, dict) else [],
        "row_level_blocker": (sync_payload or {}).get("row_level_blocker") if isinstance(sync_payload, dict) else None,
        "external_write_executed": False,
    }


def _latest_capture_run(session, *, tenant_id: int, account_id: int) -> PlatformReviewRun | None:
    return session.scalars(
        select(PlatformReviewRun)
        .where(
            PlatformReviewRun.tenant_id == tenant_id,
            PlatformReviewRun.account_proposal_id == account_id,
            PlatformReviewRun.operation == CAPTURE_WRITE_SCREEN_ACTION,
        )
        .order_by(PlatformReviewRun.id.desc())
    ).first()


def _kill_process_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, check=False)


def _summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "targets": len(rows),
        "launched": sum(1 for row in rows if row.get("launch_status") == "visible_browser_launched"),
        "captures_available": sum(1 for row in rows if row.get("capture_available")),
        "synced": sum(1 for row in rows if row.get("sync_status") == "readonly_capture_synced"),
        "mapping_proposals_created": sum(int(row.get("mapping_proposals_created") or 0) for row in rows),
        "write_paths_upserted": sum(int(row.get("write_paths_upserted") or 0) for row in rows),
        "external_write_executed": 0,
    }


def _page_routes(capture_summary: Any) -> list[str]:
    if not isinstance(capture_summary, dict):
        return []
    routes: list[str] = []
    seen: set[str] = set()
    for page in capture_summary.get("pages") or []:
        if not isinstance(page, dict):
            continue
        route = str(page.get("url") or "").strip()
        if not route or route in seen:
            continue
        seen.add(route)
        routes.append(route)
    return routes


def _editable_field_names(capture_summary: Any) -> list[str]:
    if not isinstance(capture_summary, dict):
        return []
    names: list[str] = []
    seen: set[str] = set()
    for page in capture_summary.get("pages") or []:
        if not isinstance(page, dict):
            continue
        label = str(page.get("label") or "")
        if not (label.startswith("worker-editable:") or label.startswith("known-worker-editable:")):
            continue
        field_groups = list(page.get("fields") or [])
        for form in page.get("forms") or []:
            if isinstance(form, dict):
                field_groups.extend(form.get("inputs") or [])
        for field in field_groups:
            if not isinstance(field, dict):
                continue
            name = str(field.get("name") or field.get("id") or field.get("fieldLabel") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)
    return names


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = _report_fieldnames()
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_xlsx(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = _report_fieldnames()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "mapping"
    sheet.append(fieldnames)
    for row in rows:
        sheet.append([_cell_value(row.get(field)) for field in fieldnames])
    for column_cells in sheet.columns:
        max_length = max(len(str(cell.value or "")) for cell in column_cells)
        sheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 12), 70)
    workbook.save(path)


def _cell_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _report_fieldnames() -> list[str]:
    return [
        "account_proposal_id",
        "platform_slug",
        "platform_name",
        "external_company_name",
        "account_status",
        "run_id",
        "browser_channel",
        "launch_status",
        "status_state",
        "capture_available",
        "pages_captured",
        "page_routes",
        "editable_field_names",
        "observed_workers",
        "sync_status",
        "mapping_proposals_created",
        "write_paths_upserted",
        "external_write_executed",
    ]


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Platform mapping batch",
        "",
        "Safe visible Playwright mapping. No external writes, captcha/MFA bypass, or opaque token calculation.",
        "",
        f"- Summary: `{payload['summary']}`",
        "",
        "| Platform | Account | Run | State | Capture | Sync | Write paths | Routes | Editable fields |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["rows"]:
        routes = ", ".join(row.get("page_routes") or [])
        editable_fields = ", ".join(row.get("editable_field_names") or [])
        lines.append(
            "| "
            f"{row['platform_name']} | "
            f"{row['external_company_name']} | "
            f"{row['run_id']} | "
            f"{row.get('status_state') or row.get('launch_status') or ''} | "
            f"{row['pages_captured']} pages / {row['observed_workers']} workers | "
            f"{row.get('sync_status') or ''} | "
            f"{row['write_paths_upserted']} | "
            f"{routes[:240]} | "
            f"{editable_fields[:240]} |"
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
