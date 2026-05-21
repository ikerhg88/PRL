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

from app.db.session import get_session_factory
from app.services.platform_write_probe_matrix import (
    DEFAULT_WRITE_MATRIX_OPERATIONS,
    build_platform_write_probe_matrix,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe platform write previews without external writes.")
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--company-id", type=int, default=None)
    parser.add_argument("--worker-id", type=int, default=None)
    parser.add_argument("--operations", nargs="*", default=list(DEFAULT_WRITE_MATRIX_OPERATIONS))
    parser.add_argument("--connector-dry-run", action="store_true")
    parser.add_argument("--seed", action="store_true", help="Inicializa/actualiza datos demo antes de generar la matriz.")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "artifacts" / "platform-write-probes")
    args = parser.parse_args()

    if args.seed:
        from app.db.demo_seed import create_demo_database

        create_demo_database()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with get_session_factory()() as session:
        payload = asyncio.run(
            build_platform_write_probe_matrix(
                session,
                tenant_id=args.tenant_id,
                company_id=args.company_id,
                worker_id=args.worker_id,
                operations=tuple(args.operations),
                connector_dry_run=args.connector_dry_run,
            )
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base = args.out_dir / f"platform_write_probe_{stamp}"
    json_path = base.with_suffix(".json")
    csv_path = base.with_suffix(".csv")
    md_path = base.with_suffix(".md")
    latest_json = args.out_dir / "platform_write_probe_latest.json"
    latest_csv = args.out_dir / "platform_write_probe_latest.csv"
    latest_md = args.out_dir / "platform_write_probe_latest.md"

    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    _write_csv(csv_path, payload["rows"])
    md_path.write_text(_render_markdown(payload), encoding="utf-8")
    latest_json.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_csv.write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_md.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    print(f"MD: {md_path}")
    print(json.dumps(payload["summary"], indent=2, ensure_ascii=False))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _render_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Platform write preview probe",
        "",
        "This report is generated from Hub data only. It does not execute external writes.",
        "",
        "## Summary",
        "",
        f"- Contexts: `{summary['contexts']}`",
        f"- Platforms: `{summary['platforms']}`",
        f"- Rows: `{summary['rows']}`",
        f"- Preview-ready rows: `{summary['preview_ready_rows']}`",
        f"- External writes executed: `{summary['external_writes_executed']}`",
        "",
        "## Statuses",
        "",
    ]
    for status, count in summary["statuses"].items():
        lines.append(f"- `{status}`: `{count}`")
    lines.extend(["", "## Live adapter statuses", ""])
    for status, count in summary["live_adapter_statuses"].items():
        lines.append(f"- `{status}`: `{count}`")
    lines.extend(["", "## Ready rows", ""])
    ready = [row for row in payload["rows"] if row["preview_ready"]]
    if not ready:
        lines.append("- None.")
    for row in ready[:30]:
        lines.append(
            "- "
            f"{row['platform_name']} / {row['external_company_name']} / {row['operation']}: "
            f"{row['planned_change_count']} planned changes."
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
