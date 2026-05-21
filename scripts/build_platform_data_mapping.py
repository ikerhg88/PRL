from __future__ import annotations

# ruff: noqa: E402

import argparse
import csv
import json
import os
import sys
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

from app.db.demo_seed import create_demo_database
from app.db.session import get_session_factory
from app.services.platform_data_coverage import build_platform_data_coverage


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a redacted platform+company data mapping coverage report.")
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--company-id", type=int, default=None)
    parser.add_argument("--priority-group", default="all")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "artifacts" / "platform-data-mapping")
    args = parser.parse_args()

    create_demo_database()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with get_session_factory()() as session:
        coverage = build_platform_data_coverage(
            session,
            tenant_id=args.tenant_id,
            company_id=args.company_id,
            priority_group=args.priority_group,
        )

    _write_json(args.out_dir / "platform_data_mapping.redacted.json", coverage)
    _write_csv(args.out_dir / "platform_data_mapping_coverage.redacted.csv", _coverage_rows(coverage))
    _write_csv(args.out_dir / "platform_data_mapping_pending.redacted.csv", _pending_rows(coverage))
    _write_markdown(args.out_dir / "platform_data_mapping_summary.redacted.md", coverage)

    print(
        json.dumps(
            {
                "platforms": coverage["totals"]["platforms"],
                "contexts": coverage["totals"]["contexts"],
                "approved_categories": coverage["totals"]["approved"],
                "mapped_categories": coverage["totals"]["mapped"],
                "partial_categories": coverage["totals"]["partial"],
                "missing_categories": coverage["totals"]["missing"],
                "pending_items": coverage["totals"]["pending_items"],
                "pending_red": coverage["totals"]["pending_red"],
                "pending_orange": coverage["totals"]["pending_orange"],
                "missing_required_keys": coverage["totals"]["missing_required_keys"],
                "pending_review_keys": coverage["totals"]["pending_review_keys"],
                "out_dir": str(args.out_dir.relative_to(ROOT)),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def _coverage_rows(coverage: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for context in coverage.get("contexts") or []:
        for category in context.get("categories") or []:
            rows.append(
                {
                    "platform_slug": context.get("platform_slug"),
                    "platform_name": context.get("platform_name"),
                    "account_proposal_id": context.get("account_proposal_id"),
                    "trace_label": context.get("trace_label"),
                    "external_company_name": context.get("external_company_name"),
                    "category": category.get("category_key"),
                    "category_label": category.get("label"),
                    "status": category.get("status"),
                    "mapped_count": category.get("mapped_count"),
                    "approved_count": category.get("approved_count"),
                    "observed_count": category.get("observed_count"),
                    "required_count": category.get("required_count"),
                    "missing_keys": ", ".join(category.get("missing_keys") or []),
                    "pending_review_keys": ", ".join(category.get("pending_review_keys") or []),
                    "pending_items": len(category.get("pending_items") or []),
                    "blockers": ", ".join(context.get("blockers") or []),
                    "next_action": context.get("next_action"),
                }
            )
    return rows


def _pending_rows(coverage: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for context in coverage.get("contexts") or []:
        for item in context.get("pending_items") or []:
            rows.append(
                {
                    "platform_slug": context.get("platform_slug"),
                    "platform_name": context.get("platform_name"),
                    "account_proposal_id": context.get("account_proposal_id"),
                    "trace_label": context.get("trace_label"),
                    "external_company_name": context.get("external_company_name"),
                    "pending_id": item.get("id"),
                    "scope": item.get("scope"),
                    "category": item.get("category_key"),
                    "kind": item.get("kind"),
                    "severity": item.get("severity"),
                    "standard_key": item.get("standard_key"),
                    "standard_label": item.get("standard_label"),
                    "title": item.get("title"),
                    "detail": item.get("detail"),
                    "suggested_action": item.get("suggested_action"),
                }
            )
    return rows


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if fieldnames:
            writer.writeheader()
        writer.writerows(rows)


def _write_markdown(path: Path, coverage: dict[str, Any]) -> None:
    totals = coverage["totals"]
    lines = [
        "# Platform Data Mapping Coverage",
        "",
        "Redacted report generated from Hub manifests, approved/proposed mappings and sanitized structure captures.",
        "",
        "## Safety",
        "",
        "- Read-only: yes.",
        "- External row values stored: no.",
        "- Credentials, cookies or tokens stored: no.",
        "- Captcha/MFA bypass: no.",
        "- Health data: minimized to occupational fitness fields only.",
        "",
        "## Summary",
        "",
        f"- Platforms: `{totals['platforms']}`",
        f"- Platform/company contexts: `{totals['contexts']}`",
        f"- Approved category maps: `{totals['approved']}`",
        f"- Complete but pending-review category maps: `{totals['mapped']}`",
        f"- Partial category maps: `{totals['partial']}`",
        f"- Missing category maps: `{totals['missing']}`",
        f"- Structured pending items: `{totals['pending_items']}`",
        f"- Red pending items: `{totals['pending_red']}`",
        f"- Orange pending items: `{totals['pending_orange']}`",
        f"- Missing required standard keys: `{totals['missing_required_keys']}`",
        f"- Pending-review required keys: `{totals['pending_review_keys']}`",
        "",
        "## Contexts",
        "",
    ]
    for context in coverage.get("contexts") or []:
        lines.extend(
            [
                f"### {context['trace_label']}",
                "",
                f"- Host: `{context.get('host') or 'pending'}`",
                f"- Blockers: `{', '.join(context.get('blockers') or []) or 'none'}`",
                f"- Pending items: `{context.get('pending_summary', {}).get('total', 0)}` "
                f"({context.get('pending_summary', {}).get('red', 0)} red / "
                f"{context.get('pending_summary', {}).get('orange', 0)} orange)",
                f"- Next action: {context.get('next_action')}",
                "",
                "| Category | Status | Mapped | Approved | Missing |",
                "| --- | --- | ---: | ---: | --- |",
            ]
        )
        for category in context.get("categories") or []:
            missing = ", ".join(category.get("missing_keys") or []) or "-"
            lines.append(
                f"| {category['label']} | {category['status']} | {category['mapped_count']}/{category['required_count']} | {category['approved_count']} | {missing} |"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
