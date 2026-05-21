from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is declared in backend dependencies.
    yaml = None


ROOT = Path(__file__).resolve().parents[1]

HOST_TO_PLATFORM_KEY = {
    "www.6conecta.com": "sixconecta",
    "api.6conecta.com": "sixconecta",
    "www.ctaimacae.net": "ctaima",
    "www.ctaima.com": "ctaima",
    "v5.e-coordina.com": "e_coordina",
    "link.e-coordina.com": "e_coordina",
    "resource.e-coordina.com": "e_coordina",
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

PLATFORM_KEY_ALIASES = {
    "ecoordina": "e_coordina",
    "ctaima_cae": "ctaima",
}

FIELD_ALIASES = {
    "company.legal_name": "company.name",
    "company.name": "company.name",
    "company.tax_id": "company.tax_id",
    "company.address": "company.address",
    "company.contact_email": "company.contact_email",
    "company.phone": "company.phone",
    "company.activity_cnae": "company.activity_cnae",
    "worker.first_name": "worker.first_name",
    "worker.last_name": "worker.last_name",
    "worker.identifier": "worker.identifier_value",
    "worker.identifier_value": "worker.identifier_value",
    "worker.company_id": "company.name",
    "worker.workplace_or_project": "project.name",
    "worker.job_role": "worker.work_position",
    "worker.ssn_naf_if_required": "worker.social_security_number",
    "worker.medical_fitness_status_minimized": "worker.medical_fitness_status",
    "document.local_document_type": "document.type",
    "document.external_document_type": "document.type",
    "document.safe_filename": "document.file",
    "document.file": "document.file",
    "document.sha256": "document.external_id",
    "document.issue_date": "document.issued_at",
    "document.expiry_date": "document.expires_at",
    "document.expiry_date_if_applicable": "document.expires_at",
    "document.entity_worker_id": "worker.identifier_value",
    "asset.type": "asset.type",
    "asset.identifier": "asset.identifier",
    "asset.plate": "vehicle.plate",
    "asset.serial_number": "machine.serial",
}

WRITE_OPERATIONS = {
    "sync_company_profile",
    "upsert_worker",
    "deactivate_worker",
    "upload_worker_document",
    "upload_company_document",
    "upload_machine_vehicle_document",
}

READ_OPERATIONS = {
    "read_external_status",
    "read_rejections",
    "download_receipt",
}

DEFAULT_OPERATION_REQUIRED_KEYS = {
    "read_external_status": ["document.status"],
    "read_rejections": ["document.rejection_reason"],
    "download_receipt": ["document.external_id"],
}

SENSITIVE_PROBE_KEYS = {
    "platform.login.username",
    "platform.login.password",
    "worker.identifier_value",
    "worker.social_security_number",
    "worker.medical_fitness_status",
    "worker.medical_fitness_expires_at",
    "document.file",
}


@dataclass
class PlatformFacts:
    platform_key: str
    platform_labels: set[str] = field(default_factory=set)
    hosts: set[str] = field(default_factory=set)
    capture_statuses: Counter[str] = field(default_factory=Counter)
    captcha_detected: bool = False
    mfa_detected: bool = False
    capture_standard_keys: set[str] = field(default_factory=set)
    capture_status_value_keys: set[str] = field(default_factory=set)
    contract_standard_keys: set[str] = field(default_factory=set)
    access_kinds: Counter[str] = field(default_factory=Counter)
    source_refs: set[str] = field(default_factory=set)
    manifest: dict[str, Any] | None = None
    operations: list[dict[str, Any]] = field(default_factory=list)

    @property
    def all_standard_keys(self) -> set[str]:
        return self.capture_standard_keys | self.contract_standard_keys


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a redacted platform operation readiness catalog.")
    parser.add_argument(
        "--translation-catalog",
        type=Path,
        default=ROOT / "artifacts" / "platform-translation" / "platform_translation_catalog.redacted.json",
    )
    parser.add_argument(
        "--access-fields",
        type=Path,
        default=ROOT / "artifacts" / "platform-translation" / "platform_access_fields.redacted.csv",
    )
    parser.add_argument(
        "--contracts-dir",
        type=Path,
        default=ROOT / "requisitos" / "iker_contratos_plataformas_max_scope_2026-05-18",
    )
    parser.add_argument("--out-dir", type=Path, default=ROOT / "artifacts" / "platform-operations")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    facts = build_operation_catalog(args.translation_catalog, args.access_fields, args.contracts_dir)
    catalog = render_catalog(facts)
    readiness_rows = _readiness_rows(catalog)
    captcha_rows = _captcha_rows(catalog)

    _write_json(args.out_dir / "platform_operation_catalog.redacted.json", catalog)
    _write_csv(args.out_dir / "platform_operation_readiness.redacted.csv", readiness_rows)
    _write_csv(args.out_dir / "platform_captcha_support.redacted.csv", captcha_rows)
    _write_markdown(args.out_dir / "platform_operation_summary.redacted.md", catalog)

    print(
        json.dumps(
            {
                "platforms": catalog["summary"]["platform_count"],
                "operation_entries": catalog["summary"]["operation_entry_count"],
                "write_operations_verified": catalog["summary"]["write_operations_verified"],
                "write_operations_plan_only": catalog["summary"]["write_operations_plan_only"],
                "captcha_human_assisted_platforms": catalog["summary"]["captcha_human_assisted_platforms"],
                "out_dir": str(args.out_dir.relative_to(ROOT)),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def build_operation_catalog(
    translation_catalog_path: Path,
    access_fields_path: Path,
    contracts_dir: Path,
) -> dict[str, PlatformFacts]:
    platforms: dict[str, PlatformFacts] = {}
    if translation_catalog_path.exists():
        _merge_translation_catalog(platforms, translation_catalog_path)
    if access_fields_path.exists():
        _merge_access_fields(platforms, access_fields_path)
    if contracts_dir.exists():
        _merge_contract_manifests(platforms, contracts_dir)
    return platforms


def render_catalog(platforms: dict[str, PlatformFacts]) -> dict[str, Any]:
    rendered_platforms: list[dict[str, Any]] = []
    operation_entry_count = 0
    write_plan_only = 0
    captcha_human_assisted = 0

    for platform_key, facts in sorted(platforms.items()):
        captcha_mode = _captcha_mode(facts)
        if captcha_mode in {"human_assisted_supported", "human_action_required_seen"}:
            captcha_human_assisted += 1
        operations = _render_operations(facts, captcha_mode)
        operation_entry_count += len(operations)
        write_plan_only += sum(
            1
            for operation in operations
            if operation["operation"] in WRITE_OPERATIONS and not operation["external_write_executed"]
        )
        rendered_platforms.append(
            {
                "platform_key": platform_key,
                "platform_labels": sorted(facts.platform_labels),
                "hosts": sorted(facts.hosts),
                "captcha": {
                    "mode": captcha_mode,
                    "captcha_detected_in_capture": facts.captcha_detected,
                    "mfa_detected_in_capture": facts.mfa_detected,
                    "supported_policy": "manual_human_in_browser_no_bypass",
                },
                "capture_statuses": facts.capture_statuses.most_common(),
                "field_coverage": {
                    "capture_standard_keys": sorted(facts.capture_standard_keys),
                    "contract_standard_keys": sorted(facts.contract_standard_keys),
                    "access_kinds": facts.access_kinds.most_common(),
                },
                "operation_catalog": operations,
                "write_probe_policy": _write_probe_policy(facts, captcha_mode),
                "source_refs": sorted(facts.source_refs),
            }
        )

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "safety": {
            "external_writes_executed": False,
            "captcha_bypass_supported": False,
            "captcha_mode": "human_assisted_only",
            "stores_credentials_or_tokens": False,
            "uses_private_browser_endpoints_as_api_contract": False,
        },
        "summary": {
            "platform_count": len(rendered_platforms),
            "operation_entry_count": operation_entry_count,
            "write_operations_verified": 0,
            "write_operations_plan_only": write_plan_only,
            "captcha_human_assisted_platforms": captcha_human_assisted,
        },
        "platforms": rendered_platforms,
    }


def _merge_translation_catalog(platforms: dict[str, PlatformFacts], path: Path) -> None:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    for item in catalog.get("platforms") or []:
        if not isinstance(item, dict):
            continue
        platform_key = _canonical_platform_key(str(item.get("platform_key") or ""), str(item.get("host") or ""))
        facts = _facts(platforms, platform_key)
        facts.platform_labels.add(str(item.get("platform_label") or platform_key))
        if item.get("host"):
            facts.hosts.add(str(item["host"]))
        if item.get("login_status"):
            facts.capture_statuses[str(item["login_status"])] += 1
        facts.captcha_detected = facts.captcha_detected or bool(item.get("captcha_detected"))
        facts.mfa_detected = facts.mfa_detected or bool(item.get("mfa_detected"))
        if item.get("source_ref"):
            facts.source_refs.add(str(item["source_ref"]))

    for translation in catalog.get("translations") or []:
        standard_key = str(translation.get("standard_key") or "")
        if not standard_key:
            continue
        aliases_by_platform = translation.get("aliases_by_platform")
        if not isinstance(aliases_by_platform, dict):
            continue
        for platform_key_raw, aliases in aliases_by_platform.items():
            platform_key = _canonical_platform_key(str(platform_key_raw), "")
            facts = _facts(platforms, platform_key)
            if not isinstance(aliases, list):
                continue
            for alias in aliases:
                if not isinstance(alias, dict):
                    continue
                source = str(alias.get("source") or "")
                if source == "capture":
                    facts.capture_standard_keys.add(standard_key)
                    if alias.get("label_kind") == "status_value":
                        facts.capture_status_value_keys.add(standard_key)
                elif source == "contract_mapping":
                    facts.contract_standard_keys.add(standard_key)
                else:
                    facts.contract_standard_keys.add(standard_key)
                if alias.get("host"):
                    facts.hosts.add(str(alias["host"]))
                if alias.get("source_ref"):
                    facts.source_refs.add(str(alias["source_ref"]))


def _merge_access_fields(platforms: dict[str, PlatformFacts], path: Path) -> None:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            platform_key = _canonical_platform_key(str(row.get("platform_key") or ""), str(row.get("host") or ""))
            facts = _facts(platforms, platform_key)
            if row.get("platform_label"):
                facts.platform_labels.add(str(row["platform_label"]))
            if row.get("host"):
                facts.hosts.add(str(row["host"]))
            if row.get("access_kind"):
                facts.access_kinds[str(row["access_kind"])] += 1
            if row.get("standard_key"):
                facts.capture_standard_keys.add(str(row["standard_key"]))
            if row.get("source_ref"):
                facts.source_refs.add(str(row["source_ref"]))


def _merge_contract_manifests(platforms: dict[str, PlatformFacts], contracts_dir: Path) -> None:
    for manifest_path in sorted(contracts_dir.glob("*/03_rpa_manifest.yaml")):
        manifest = _load_yaml(manifest_path)
        platform = manifest.get("platform") if isinstance(manifest.get("platform"), dict) else {}
        hosts = platform.get("hosts") if isinstance(platform.get("hosts"), list) else []
        platform_key = _platform_key_from_manifest(platform, hosts)
        facts = _facts(platforms, platform_key)
        facts.manifest = manifest
        if platform.get("name"):
            facts.platform_labels.add(str(platform["name"]))
        for host in hosts:
            facts.hosts.add(str(host))
        facts.source_refs.add(str(manifest_path.relative_to(ROOT)))
        for operation in manifest.get("operations") or []:
            if not isinstance(operation, dict):
                continue
            facts.operations.append(operation)
            for key in _canonical_fields(operation.get("required_fields")):
                facts.contract_standard_keys.add(key)
            for key in _canonical_fields(operation.get("optional_fields")):
                facts.contract_standard_keys.add(key)


def _render_operations(facts: PlatformFacts, captcha_mode: str) -> list[dict[str, Any]]:
    operations = facts.operations
    if not operations and "document.status" in facts.capture_standard_keys:
        operations = [
            {
                "operation": "read_external_status",
                "entity": "external_document_status",
                "required_fields": ["document.status"],
                "optional_fields": ["document.expires_at", "document.rejection_reason"],
                "requires_preview": True,
                "requires_manual_approval": False,
            }
        ]
    rendered: list[dict[str, Any]] = []
    for operation in operations:
        operation_name = str(operation.get("operation") or "")
        if not operation_name:
            continue
        operation_name = str(operation.get("operation") or "")
        required = _canonical_fields(operation.get("required_fields"))
        if not required:
            required = list(DEFAULT_OPERATION_REQUIRED_KEYS.get(operation_name, []))
        optional = _canonical_fields(operation.get("optional_fields"))
        capture_missing = sorted(key for key in required if key not in facts.capture_standard_keys)
        contract_missing = sorted(key for key in required if key not in facts.all_standard_keys)
        readiness = _operation_readiness(
            operation_name=operation_name,
            facts=facts,
            required=required,
            capture_missing=capture_missing,
            contract_missing=contract_missing,
        )
        rendered.append(
            {
                "operation": operation_name,
                "entity": operation.get("entity"),
                "readiness": readiness,
                "proof_level": _proof_level(operation_name, readiness),
                "required_canonical_fields": required,
                "optional_canonical_fields": optional,
                "missing_required_in_capture": capture_missing,
                "missing_required_in_contract": contract_missing,
                "requires_preview": bool(operation.get("requires_preview", True)),
                "requires_manual_approval": bool(operation.get("requires_manual_approval", True)),
                "dry_run_required": True,
                "manual_approval_required": True,
                "captcha_mode": captcha_mode,
                "external_write_executed": False,
                "expected_confirmation": operation.get("expected_confirmation"),
                "screens_or_steps_expected": operation.get("screens_or_steps_expected") or [],
            }
        )
    return rendered


def _operation_readiness(
    *,
    operation_name: str,
    facts: PlatformFacts,
    required: list[str],
    capture_missing: list[str],
    contract_missing: list[str],
) -> str:
    has_successful_capture = any(status.startswith("login_likely_success") for status in facts.capture_statuses)
    if (
        operation_name == "read_external_status"
        and "document.status" in facts.capture_status_value_keys
        and has_successful_capture
    ):
        return "verified_readonly_status_counts_available"
    if operation_name in READ_OPERATIONS:
        if contract_missing:
            return "proposal_missing_required_contract_fields"
        if capture_missing:
            return "contract_proposed_needs_readonly_path_validation"
        return "readonly_mapping_ready"
    if operation_name in WRITE_OPERATIONS:
        if contract_missing:
            return "proposal_missing_required_contract_fields"
        if not has_successful_capture:
            return "contract_proposed_needs_login_validation"
        if capture_missing:
            return "contract_proposed_needs_write_screen_mapping"
        return "dry_run_mapping_ready_needs_reversible_write_probe"
    return "cataloged_proposal"


def _proof_level(operation_name: str, readiness: str) -> str:
    if readiness == "verified_readonly_status_counts_available":
        return "live_readonly_verified"
    if operation_name in WRITE_OPERATIONS:
        return "not_write_verified_no_external_save_executed"
    if readiness.startswith("contract_proposed"):
        return "contract_proposal_plus_redacted_capture"
    return "cataloged"


def _write_probe_policy(facts: PlatformFacts, captcha_mode: str) -> dict[str, Any]:
    candidate_keys = sorted(
        key
        for key in facts.capture_standard_keys
        if key not in SENSITIVE_PROBE_KEYS and (key.startswith("company.") or key.startswith("worker."))
    )
    has_successful_capture = any(status.startswith("login_likely_success") for status in facts.capture_statuses)
    status = "requires_dummy_entity_or_provider_sandbox"
    if not has_successful_capture:
        status = "blocked_until_login_validated"
    elif not candidate_keys:
        status = "blocked_until_editable_low_risk_field_mapped"
    return {
        "status": status,
        "external_write_executed": False,
        "candidate_low_risk_standard_keys": candidate_keys[:20],
        "captcha_mode": captcha_mode,
        "required_sequence": [
            "create_or_select_dummy_entity_inside_authorized_company",
            "capture_before_value_redacted",
            "change_one_low_risk_field_to_unique_probe_value",
            "save_with_manual_approval",
            "verify_saved_state_redacted",
            "restore_original_value",
            "verify_restored_state_redacted",
            "record_before_after_and_restore_audit",
        ],
    }


def _captcha_mode(facts: PlatformFacts) -> str:
    if facts.captcha_detected or facts.mfa_detected:
        return "human_action_required_seen"
    if any(status.startswith("human_action_required") for status in facts.capture_statuses):
        return "human_action_required_seen"
    if any("stopped_control" in status for status in facts.capture_statuses):
        return "human_action_required_seen"
    platform = facts.manifest.get("platform") if isinstance(facts.manifest, dict) else {}
    if isinstance(platform, dict) and platform.get("rpa_assisted_on_captcha_mfa_or_notice"):
        return "human_assisted_supported"
    if facts.capture_statuses:
        return "not_seen_in_capture"
    return "policy_required_not_live_validated"


def _canonical_fields(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    keys: list[str] = []
    for value in values:
        key = _canonical_field_key(str(value))
        if key and key not in keys:
            keys.append(key)
    return keys


def _canonical_field_key(value: str) -> str | None:
    clean = value.strip()
    clean = re.sub(r"_if_(applicable|required|available)$", "", clean)
    clean = re.sub(r"_minimized_if_applicable$", "", clean)
    if clean in FIELD_ALIASES:
        return FIELD_ALIASES[clean]
    if value in FIELD_ALIASES:
        return FIELD_ALIASES[value]
    if clean.startswith(("company.", "worker.", "document.", "asset.", "vehicle.", "machine.", "project.")):
        return clean
    return None


def _facts(platforms: dict[str, PlatformFacts], platform_key: str) -> PlatformFacts:
    key = _canonical_platform_key(platform_key, "")
    if key not in platforms:
        platforms[key] = PlatformFacts(platform_key=key)
    return platforms[key]


def _platform_key_from_manifest(platform: dict[str, Any], hosts: list[Any]) -> str:
    platform_id = str(platform.get("id") or "")
    if platform_id:
        return _canonical_platform_key(platform_id, "")
    for host in hosts:
        host_key = _canonical_platform_key("", str(host))
        if host_key:
            return host_key
    return _canonical_platform_key(str(platform.get("name") or "unknown"), "")


def _canonical_platform_key(value: str, host: str) -> str:
    host_l = (host or "").lower()
    parsed = urlparse(host_l)
    host_clean = parsed.netloc or host_l
    if host_clean in HOST_TO_PLATFORM_KEY:
        return HOST_TO_PLATFORM_KEY[host_clean]
    key = re.sub(r"[^a-zA-Z0-9]+", "_", (value or host_clean or "unknown").lower()).strip("_")
    key = PLATFORM_KEY_ALIASES.get(key, key)
    return key[:80] or "unknown"


def _load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _readiness_rows(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for platform in catalog["platforms"]:
        for operation in platform["operation_catalog"]:
            rows.append(
                {
                    "platform_key": platform["platform_key"],
                    "platform_labels": "; ".join(platform["platform_labels"][:3]),
                    "hosts": "; ".join(platform["hosts"][:3]),
                    "operation": operation["operation"],
                    "entity": operation.get("entity") or "",
                    "readiness": operation["readiness"],
                    "proof_level": operation["proof_level"],
                    "captcha_mode": operation["captcha_mode"],
                    "required_fields": "; ".join(operation["required_canonical_fields"]),
                    "missing_required_in_capture": "; ".join(operation["missing_required_in_capture"]),
                    "missing_required_in_contract": "; ".join(operation["missing_required_in_contract"]),
                    "dry_run_required": operation["dry_run_required"],
                    "manual_approval_required": operation["manual_approval_required"],
                    "external_write_executed": operation["external_write_executed"],
                }
            )
    return rows


def _captcha_rows(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for platform in catalog["platforms"]:
        rows.append(
            {
                "platform_key": platform["platform_key"],
                "platform_labels": "; ".join(platform["platform_labels"][:3]),
                "hosts": "; ".join(platform["hosts"][:3]),
                "captcha_mode": platform["captcha"]["mode"],
                "captcha_detected_in_capture": platform["captcha"]["captcha_detected_in_capture"],
                "mfa_detected_in_capture": platform["captcha"]["mfa_detected_in_capture"],
                "supported_policy": platform["captcha"]["supported_policy"],
                "capture_statuses": "; ".join(f"{status}:{count}" for status, count in platform["capture_statuses"]),
                "write_probe_status": platform["write_probe_policy"]["status"],
                "external_write_executed": platform["write_probe_policy"]["external_write_executed"],
            }
        )
    return rows


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(path: Path, catalog: dict[str, Any]) -> None:
    summary = catalog["summary"]
    lines = [
        "# Platform Operation Summary",
        "",
        f"- Generated UTC: `{catalog['generated_at_utc']}`",
        f"- Platforms: `{summary['platform_count']}`",
        f"- Operation entries: `{summary['operation_entry_count']}`",
        f"- Write operations verified: `{summary['write_operations_verified']}`",
        f"- Write operations plan-only: `{summary['write_operations_plan_only']}`",
        f"- Captcha/MFA human-assisted platforms: `{summary['captcha_human_assisted_platforms']}`",
        "",
        "## Safety",
        "",
        "- No external writes were executed.",
        "- Captcha/MFA support is human-assisted only; bypass is not supported.",
        "- Browser endpoints observed in captures are not API contracts.",
        "- A reversible field probe requires dummy/sandbox data, approval and before/after/revert audit.",
        "",
        "## Readiness Counts",
        "",
    ]
    readiness = Counter(
        operation["readiness"]
        for platform in catalog["platforms"]
        for operation in platform["operation_catalog"]
    )
    for key, count in readiness.most_common():
        lines.append(f"- `{key}`: {count}")
    lines.extend(["", "## Confirmed Live Read-Only", ""])
    confirmed = [
        (platform["platform_key"], operation["operation"])
        for platform in catalog["platforms"]
        for operation in platform["operation_catalog"]
        if operation["readiness"] == "verified_readonly_status_counts_available"
    ]
    if confirmed:
        for platform_key, operation in confirmed:
            lines.append(f"- `{platform_key}`: `{operation}`")
    else:
        lines.append("- None.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
