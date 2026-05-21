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
os.environ.setdefault("IPRL_CAE_DATABASE_URL", f"sqlite:///{(ROOT / 'storage' / 'demo.db').as_posix()}")
os.environ.setdefault("IPRL_CAE_DOCUMENT_STORAGE_PATH", str(ROOT / "storage" / "documents"))
os.environ.setdefault("IPRL_CAE_SECRET_KEY", "local-demo-secret-key-for-development-only-32")

from sqlalchemy import select

from app.db.demo_seed import create_demo_database
from app.db.models import Company, ExternalPlatform, PlatformDiscoveredLabel, PlatformStructureSnapshot, User
from app.db.session import get_session_factory
from app.services.audit import public_state, record_audit
from app.services.platform_mapping import extract_labels_from_capture


HOST_TO_PLATFORM_KEY = {
    "www.6conecta.com": "sixconecta",
    "api.6conecta.com": "sixconecta",
    "www.ctaimacae.net": "ctaima_cae",
    "v5.e-coordina.com": "ecoordina",
    "secure.validate.network": "validate",
    "www.dokyfy.net": "dokify",
    "www.dokify.net": "dokify",
    "www.gestion.iedoce.com": "iedoce",
    "integra.asemwebservices.es": "asemwebservices_integra",
    "sgs.sgs-gestiona.es": "sgs_gestiona",
    "seat.folyo.es": "folyo",
    "u5.ucae.es": "ucae",
    "cae.vitaly.es": "vitaly_cae",
    "tiautomotive.smartosh.com": "smartosh",
    "gestamp-abrera.smartosh.com": "smartosh",
    "timenet.gpisoftware.com": "timenet",
    "app.nomio.io": "nomio",
    "quioo.es": "quioo",
    "www.metacontratas.com": "metacontratas",
    "fagorederlan.egestiona.es": "egestiona",
    "faurecia.egestiona.com": "egestiona",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Import redacted ARM platform captures into platform map tables.")
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--company-tax-id", default="B95868543")
    parser.add_argument("--captures-dir", default=str(ROOT / "artifacts" / "platform-captures"))
    parser.add_argument("--replace", action="store_true", help="Replace existing snapshots with the same source_ref.")
    args = parser.parse_args()

    create_demo_database()
    captures_dir = Path(args.captures_dir)
    summary = _load_capture_entries(captures_dir)

    session_factory = get_session_factory()
    imported = 0
    skipped = 0
    labels_created = 0
    with session_factory() as session:
        actor = session.scalar(
            select(User).where(User.tenant_id == args.tenant_id, User.email == "demo@demo.invalid")
        )
        company = session.scalar(
            select(Company).where(Company.tenant_id == args.tenant_id, Company.tax_id == args.company_tax_id)
        )
        platform_by_key = {
            item.platform_key: item
            for item in session.scalars(select(ExternalPlatform))
        }
        for entry in summary:
            json_ref = entry.get("json")
            if not isinstance(json_ref, str) or not json_ref:
                skipped += 1
                continue
            capture_path = (ROOT / json_ref).resolve()
            if not capture_path.exists():
                skipped += 1
                continue
            source_ref = str(capture_path.relative_to(ROOT))
            existing = session.scalar(
                select(PlatformStructureSnapshot).where(
                    PlatformStructureSnapshot.tenant_id == args.tenant_id,
                    PlatformStructureSnapshot.source_ref == source_ref,
                )
            )
            if existing is not None:
                if not args.replace:
                    skipped += 1
                    continue
                session.query(PlatformDiscoveredLabel).filter(
                    PlatformDiscoveredLabel.tenant_id == args.tenant_id,
                    PlatformDiscoveredLabel.snapshot_id == existing.id,
                ).delete()
                session.delete(existing)
                session.flush()

            capture = json.loads(capture_path.read_text(encoding="utf-8"))
            host = str(entry.get("host") or (capture.get("source") or {}).get("initial_host") or "").lower()
            platform_key = HOST_TO_PLATFORM_KEY.get(host)
            platform = platform_by_key.get(platform_key) if platform_key else None
            snapshot = PlatformStructureSnapshot(
                tenant_id=args.tenant_id,
                external_platform_id=platform.id if platform else None,
                platform_account_id=None,
                company_id=company.id if company else None,
                platform_label=str(entry.get("label") or (capture.get("source") or {}).get("platform_label") or host),
                host=host or None,
                login_status=str(entry.get("login_status") or (capture.get("outcome") or {}).get("login_status") or ""),
                source_type="readonly_capture",
                source_ref=source_ref,
                status="mapped",
                structure_json=capture,
                summary_json={
                    "row": entry.get("row"),
                    "pages_captured": entry.get("pages_captured"),
                    "captcha_detected": entry.get("captcha_detected"),
                    "mfa_detected": entry.get("mfa_detected"),
                    "platform_key": platform_key,
                },
                created_by=actor.id if actor else None,
            )
            session.add(snapshot)
            session.flush()
            extracted = extract_labels_from_capture(capture)
            for label in extracted:
                session.add(
                    PlatformDiscoveredLabel(
                        tenant_id=args.tenant_id,
                        snapshot_id=snapshot.id,
                        external_platform_id=snapshot.external_platform_id,
                        platform_account_id=None,
                        company_id=snapshot.company_id,
                        label_kind=label.label_kind,
                        raw_label=label.raw_label,
                        normalized_label=label.normalized_label,
                        page_label=label.page_label,
                        entity_scope=label.entity_scope,
                        standard_key=label.standard_key,
                        confidence=label.confidence,
                        review_status="proposed" if label.standard_key else "needs_review",
                        metadata_json=label.metadata,
                    )
                )
            labels_created += len(extracted)
            imported += 1
        record_audit(
            session,
            tenant_id=args.tenant_id,
            actor_user_id=actor.id if actor else None,
            action="platform_structure.arm_capture_import",
            entity_type="platform_structure_snapshot",
            entity_id=None,
            after=public_state({"imported": imported, "skipped": skipped, "labels_created": labels_created}),
        )
        session.commit()
    print(json.dumps({"imported": imported, "skipped": skipped, "labels_created": labels_created}, indent=2))


def _load_capture_entries(captures_dir: Path) -> list[dict[str, object]]:
    summary_path = captures_dir / "arm_capture_summary.redacted.json"
    entries: list[dict[str, object]] = []
    if summary_path.exists():
        entries.extend(json.loads(summary_path.read_text(encoding="utf-8")))
    known = {str(entry.get("json")) for entry in entries}
    for path in sorted(captures_dir.glob("**/technical_capture.redacted.json")):
        rel = str(path.relative_to(ROOT))
        if rel in known:
            continue
        capture = json.loads(path.read_text(encoding="utf-8"))
        source = capture.get("source") if isinstance(capture.get("source"), dict) else {}
        outcome = capture.get("outcome") if isinstance(capture.get("outcome"), dict) else {}
        entries.append(
            {
                "row": source.get("row"),
                "label": source.get("platform_label") or path.parent.name,
                "host": source.get("initial_host"),
                "login_status": outcome.get("login_status"),
                "captcha_detected": outcome.get("captcha_detected"),
                "mfa_detected": outcome.get("mfa_detected"),
                "pages_captured": len(capture.get("pages") or []),
                "json": rel,
            }
        )
    return entries


if __name__ == "__main__":
    main()
