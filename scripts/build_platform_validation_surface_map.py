from __future__ import annotations

# ruff: noqa: E402

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("IPRL_CAE_CONFIG_FILE", str(ROOT / "config" / "iprl-cae.local.example.toml"))
os.environ.setdefault("IPRL_CAE_ENVIRONMENT", "local")

from app.services.platform_validation_surfaces import (
    build_validation_surface_map,
    write_validation_surface_artifacts,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a redacted map of validation, notification and readback surfaces."
    )
    parser.add_argument("--capture-root", type=Path, default=ROOT / "artifacts" / "platform-captures")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "artifacts" / "platform-validation-surfaces")
    parser.add_argument("--include-all", action="store_true")
    args = parser.parse_args()

    payload = build_validation_surface_map(
        capture_root=args.capture_root,
        current_only=not args.include_all,
    )
    outputs = write_validation_surface_artifacts(payload, out_dir=args.out_dir)
    print(
        json.dumps(
            {
                "platforms": payload["totals"]["platforms"],
                "captures_used": payload["totals"]["capture_files_used"],
                "surfaces": payload["totals"]["surfaces"],
                "outputs": outputs,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
