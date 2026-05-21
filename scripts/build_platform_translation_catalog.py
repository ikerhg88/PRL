from __future__ import annotations

# ruff: noqa: E402

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("IPRL_CAE_CONFIG_FILE", str(ROOT / "config" / "iprl-cae.local.example.toml"))
os.environ.setdefault("IPRL_CAE_ENVIRONMENT", "local")

from app.services.platform_mapping import (  # noqa: E402
    STANDARD_LABELS,
    extract_labels_from_capture,
    infer_standard_label,
    normalize_label,
)

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is present in the backend env.
    yaml = None


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

CANONICAL_FIELD_ALIASES = {
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
    "asset.type": "asset.type",
    "asset.identifier": "asset.identifier",
    "asset.plate": "vehicle.plate",
    "asset.serial_number": "machine.serial",
}

SECRET_HINTS = (
    "password",
    "passwd",
    "pass",
    "contrase",
    "clave",
    "token",
    "secret",
    "cookie",
    "session",
    "authorization",
    "auth",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build redacted platform access and translation catalogs.")
    parser.add_argument("--captures-dir", type=Path, default=ROOT / "artifacts" / "platform-captures")
    parser.add_argument(
        "--contracts-dir",
        type=Path,
        default=ROOT / "requisitos" / "iker_contratos_plataformas_max_scope_2026-05-18",
    )
    parser.add_argument("--out-dir", type=Path, default=ROOT / "artifacts" / "platform-translation")
    parser.add_argument("--include-extra-captures", action="store_true", default=True)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    capture_entries = _load_capture_entries(args.captures_dir)
    label_rows: list[dict[str, Any]] = []
    access_rows: list[dict[str, Any]] = []
    platform_summaries: list[dict[str, Any]] = []

    for entry in capture_entries:
        capture_path = (ROOT / entry["json"]).resolve()
        if not capture_path.exists():
            continue
        capture = json.loads(capture_path.read_text(encoding="utf-8"))
        platform_label = _redact_text(str(entry.get("label") or (capture.get("source") or {}).get("platform_label") or ""))
        host = str(entry.get("host") or (capture.get("source") or {}).get("initial_host") or "").lower()
        platform_key = _platform_key(host, platform_label)
        source_ref = str(capture_path.relative_to(ROOT))
        labels = extract_labels_from_capture(capture)
        for label in labels:
            label_rows.append(
                {
                    "source": "capture",
                    "source_ref": source_ref,
                    "row": entry.get("row"),
                    "platform_key": platform_key,
                    "platform_label": platform_label,
                    "host": host,
                    "login_status": entry.get("login_status") or (capture.get("outcome") or {}).get("login_status"),
                    "label_kind": label.label_kind,
                    "raw_label": _redact_text(label.raw_label),
                    "normalized_label": label.normalized_label,
                    "page_label": _redact_text(label.page_label),
                    "entity_scope": label.entity_scope,
                    "standard_key": label.standard_key,
                    "confidence": label.confidence,
                    "review_status": "proposed" if label.standard_key else "needs_review",
                    "metadata": _safe_metadata(label.metadata),
                }
            )
        platform_access_rows, platform_summary = _capture_access_rows(
            capture=capture,
            entry=entry,
            platform_key=platform_key,
            platform_label=platform_label,
            host=host,
            source_ref=source_ref,
        )
        access_rows.extend(platform_access_rows)
        platform_summaries.append(platform_summary)

    contract_rows = _contract_mapping_rows(args.contracts_dir)
    label_rows.extend(contract_rows)

    catalog = _build_catalog(label_rows, access_rows, platform_summaries)
    _write_json(args.out_dir / "platform_translation_catalog.redacted.json", catalog)
    _write_csv(args.out_dir / "platform_translation_aliases.redacted.csv", _alias_csv_rows(label_rows))
    _write_csv(args.out_dir / "platform_access_fields.redacted.csv", access_rows)
    _write_csv(args.out_dir / "platform_summary.redacted.csv", _platform_summary_csv_rows(platform_summaries))
    _write_markdown(args.out_dir / "platform_translation_summary.redacted.md", catalog)

    print(
        json.dumps(
            {
                "captures_processed": len(capture_entries),
                "platforms": catalog["summary"]["platform_count"],
                "translation_aliases": catalog["summary"]["translation_alias_count"],
                "access_fields": len(access_rows),
                "out_dir": str(args.out_dir.relative_to(ROOT)),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def _load_capture_entries(captures_dir: Path) -> list[dict[str, Any]]:
    summary_path = captures_dir / "arm_capture_summary.redacted.json"
    entries: list[dict[str, Any]] = []
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


def _capture_access_rows(
    *,
    capture: dict[str, Any],
    entry: dict[str, Any],
    platform_key: str,
    platform_label: str,
    host: str,
    source_ref: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    nav_labels: set[str] = set()
    page_count = 0
    form_count = 0
    table_count = 0
    grid_count = 0
    field_count = 0
    for page_index, page in enumerate(capture.get("pages") or []):
        if not isinstance(page, dict):
            continue
        page_count += 1
        page_label = _redact_text(str(page.get("label") or page.get("title") or f"page-{page_index}"))
        for nav in _string_list(page.get("nav_labels")):
            nav_labels.add(_redact_text(nav))
            rows.append(
                _access_row(
                    platform_key,
                    platform_label,
                    host,
                    source_ref,
                    page_label,
                    "nav",
                    nav,
                    None,
                    None,
                    None,
                )
            )
        for header in _string_list(page.get("grid_headers")):
            grid_count += 1
            rows.append(
                _access_row(
                    platform_key,
                    platform_label,
                    host,
                    source_ref,
                    page_label,
                    "grid_header",
                    header,
                    None,
                    None,
                    None,
                )
            )
        for headers in page.get("table_headers") or []:
            if not isinstance(headers, list):
                continue
            table_count += 1
            for header in _string_list(headers):
                rows.append(
                    _access_row(
                        platform_key,
                        platform_label,
                        host,
                        source_ref,
                        page_label,
                        "table_header",
                        header,
                        None,
                        None,
                        None,
                    )
                )
        for grid in page.get("grid_columns") or []:
            if not isinstance(grid, dict):
                continue
            grid_count += 1
            for column in grid.get("columns") or []:
                if not isinstance(column, dict):
                    continue
                raw = column.get("header") or column.get("data_index")
                if raw:
                    rows.append(
                        _access_row(
                            platform_key,
                            platform_label,
                            host,
                            source_ref,
                            page_label,
                            "grid_column",
                            str(raw),
                            column.get("data_index"),
                            None,
                            column.get("hidden"),
                        )
                    )
        for form_index, form in enumerate(page.get("forms") or []):
            if not isinstance(form, dict):
                continue
            form_count += 1
            for input_item in form.get("inputs") or []:
                if not isinstance(input_item, dict):
                    continue
                raw = _first_nonempty(
                    input_item.get("ariaLabel"),
                    input_item.get("placeholder"),
                    input_item.get("name"),
                    input_item.get("id"),
                    input_item.get("type"),
                )
                if raw:
                    field_count += 1
                    rows.append(
                        _access_row(
                            platform_key,
                            platform_label,
                            host,
                            source_ref,
                            page_label,
                            "form_field",
                            raw,
                            input_item.get("name") or input_item.get("id"),
                            input_item.get("type") or input_item.get("tag"),
                            input_item.get("required"),
                            form_index=form_index,
                        )
                    )
            for button in form.get("buttons") or []:
                if not isinstance(button, dict):
                    continue
                raw = _first_nonempty(button.get("text"), button.get("name"), button.get("id"))
                if raw:
                    rows.append(
                        _access_row(
                            platform_key,
                            platform_label,
                            host,
                            source_ref,
                            page_label,
                            "button",
                            raw,
                            button.get("name") or button.get("id"),
                            button.get("type"),
                            None,
                            form_index=form_index,
                        )
                    )
    summary = {
        "row": entry.get("row"),
        "platform_key": platform_key,
        "platform_label": platform_label,
        "host": host,
        "login_status": entry.get("login_status") or (capture.get("outcome") or {}).get("login_status"),
        "captcha_detected": bool(entry.get("captcha_detected") or (capture.get("outcome") or {}).get("captcha_detected")),
        "mfa_detected": bool(entry.get("mfa_detected") or (capture.get("outcome") or {}).get("mfa_detected")),
        "page_count": page_count,
        "nav_count": len(nav_labels),
        "form_count": form_count,
        "field_count": field_count,
        "table_count": table_count,
        "grid_count": grid_count,
        "source_ref": source_ref,
    }
    return rows, summary


def _access_row(
    platform_key: str,
    platform_label: str,
    host: str,
    source_ref: str,
    page_label: str,
    access_kind: str,
    raw_label: str,
    field_name: object,
    field_type: object,
    required_or_hidden: object,
    *,
    form_index: int | None = None,
) -> dict[str, Any]:
    clean_label = _redact_text(raw_label)
    standard_key, entity_scope, confidence = infer_standard_label(clean_label, page_context=page_label, label_kind=access_kind)
    return {
        "platform_key": platform_key,
        "platform_label": platform_label,
        "host": host,
        "source_ref": source_ref,
        "page_label": page_label,
        "access_kind": access_kind,
        "raw_label": clean_label,
        "normalized_label": normalize_label(clean_label),
        "field_name": _redact_text(field_name),
        "field_type": _redact_text(field_type),
        "required_or_hidden": "" if required_or_hidden is None else str(required_or_hidden),
        "form_index": "" if form_index is None else str(form_index),
        "entity_scope": entity_scope,
        "standard_key": standard_key,
        "confidence": confidence,
    }


def _contract_mapping_rows(contracts_dir: Path) -> list[dict[str, Any]]:
    if yaml is None or not contracts_dir.exists():
        return []
    rows: list[dict[str, Any]] = []
    for mappings_path in sorted(contracts_dir.glob("*/04_mappings.yaml")):
        manifest_path = mappings_path.with_name("03_rpa_manifest.yaml")
        mappings_data = _load_yaml(mappings_path)
        manifest_data = _load_yaml(manifest_path) if manifest_path.exists() else {}
        platform = manifest_data.get("platform") if isinstance(manifest_data.get("platform"), dict) else {}
        platform_id = str(platform.get("id") or mappings_data.get("platform_id") or mappings_path.parent.name)
        platform_name = str(platform.get("name") or platform_id)
        hosts = platform.get("hosts") if isinstance(platform.get("hosts"), list) else []
        host = str(hosts[0]).lower() if hosts else ""
        field_mappings = mappings_data.get("field_mappings") if isinstance(mappings_data.get("field_mappings"), dict) else {}
        for entity_scope, items in field_mappings.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                iker_field = str(item.get("iker_field") or "")
                external_label = str(item.get("external_label_or_field_proposed") or "")
                if not external_label:
                    continue
                canonical_key = CANONICAL_FIELD_ALIASES.get(iker_field)
                if canonical_key is None:
                    inferred_key, _scope, _confidence = infer_standard_label(external_label, label_kind="contract_field")
                    canonical_key = inferred_key
                rows.append(
                    {
                        "source": "contract_mapping",
                        "source_ref": str(mappings_path.relative_to(ROOT)),
                        "row": "",
                        "platform_key": _platform_key(host, platform_id),
                        "platform_label": _redact_text(platform_name),
                        "host": host,
                        "login_status": "not_live_capture",
                        "label_kind": "contract_field",
                        "raw_label": _redact_text(external_label),
                        "normalized_label": normalize_label(external_label),
                        "page_label": "",
                        "entity_scope": str(entity_scope),
                        "standard_key": canonical_key,
                        "confidence": 60 if canonical_key else 0,
                        "review_status": "contract_proposed",
                        "metadata": {
                            "iker_field": iker_field,
                            "requirement": item.get("requirement"),
                            "status": item.get("status"),
                        },
                    }
                )
    return rows


def _build_catalog(
    label_rows: list[dict[str, Any]],
    access_rows: list[dict[str, Any]],
    platform_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unmapped: list[dict[str, Any]] = []
    for row in label_rows:
        if row.get("standard_key"):
            by_key[str(row["standard_key"])].append(row)
        else:
            unmapped.append(row)

    standard_labels = {item.key: asdict(item) for item in STANDARD_LABELS}
    translations: list[dict[str, Any]] = []
    for standard_key, rows in sorted(by_key.items()):
        aliases_by_platform: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            platform = row.get("platform_key") or row.get("platform_label") or "unknown"
            aliases_by_platform[str(platform)].append(
                {
                    "raw_label": row.get("raw_label"),
                    "label_kind": row.get("label_kind"),
                    "source": row.get("source"),
                    "source_ref": row.get("source_ref"),
                    "page_label": row.get("page_label"),
                    "confidence": row.get("confidence"),
                    "review_status": row.get("review_status"),
                    "host": row.get("host"),
                }
            )
        translations.append(
            {
                "standard_key": standard_key,
                "standard_label": standard_labels.get(standard_key),
                "platform_count": len(aliases_by_platform),
                "alias_count": len(rows),
                "aliases_by_platform": dict(sorted(aliases_by_platform.items())),
            }
        )

    capture_platform_count = len({(item.get("platform_key"), item.get("host")) for item in platform_summaries})
    translation_platform_count = len(
        {row.get("platform_key") or row.get("platform_label") for row in label_rows if row.get("platform_key") or row.get("platform_label")}
    )
    login_statuses = Counter(str(item.get("login_status")) for item in platform_summaries)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "safety": {
            "credentials_included": False,
            "cookies_tokens_har_bodies_included": False,
            "row_values_included": False,
            "source": "redacted captures and contract manifests only",
        },
        "summary": {
            "platform_count": translation_platform_count,
            "capture_platform_count": capture_platform_count,
            "capture_count": len(platform_summaries),
            "login_statuses": login_statuses.most_common(),
            "translation_key_count": len(translations),
            "translation_alias_count": sum(item["alias_count"] for item in translations),
            "unmapped_label_count": len(unmapped),
            "access_field_count": len(access_rows),
        },
        "standard_labels": list(standard_labels.values()),
        "platforms": sorted(platform_summaries, key=lambda item: (str(item.get("platform_key")), str(item.get("platform_label")))),
        "translations": translations,
        "unmapped_labels_sample": _unmapped_sample(unmapped),
    }


def _alias_csv_rows(label_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = [
        "source",
        "platform_key",
        "platform_label",
        "host",
        "standard_key",
        "entity_scope",
        "raw_label",
        "normalized_label",
        "label_kind",
        "page_label",
        "confidence",
        "review_status",
        "source_ref",
    ]
    return [{key: row.get(key, "") for key in keys} for row in label_rows]


def _platform_summary_csv_rows(platform_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = [
        "row",
        "platform_key",
        "platform_label",
        "host",
        "login_status",
        "captcha_detected",
        "mfa_detected",
        "page_count",
        "nav_count",
        "form_count",
        "field_count",
        "table_count",
        "grid_count",
        "source_ref",
    ]
    return [{key: item.get(key, "") for key in keys} for item in platform_summaries]


def _unmapped_sample(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sample: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        key = (str(row.get("platform_key")), str(row.get("raw_label")), str(row.get("label_kind")))
        if key in seen:
            continue
        seen.add(key)
        sample.append(
            {
                "platform_key": row.get("platform_key"),
                "platform_label": row.get("platform_label"),
                "label_kind": row.get("label_kind"),
                "raw_label": row.get("raw_label"),
                "source_ref": row.get("source_ref"),
            }
        )
        if len(sample) >= 200:
            break
    return sample


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(path: Path, catalog: dict[str, Any]) -> None:
    summary = catalog["summary"]
    lines = [
        "# Platform Translation Summary",
        "",
        f"- Generated UTC: `{catalog['generated_at_utc']}`",
        f"- Platforms in translation catalog: `{summary['platform_count']}`",
        f"- Platforms with redacted captures: `{summary['capture_platform_count']}`",
        f"- Captures: `{summary['capture_count']}`",
        f"- Translation keys: `{summary['translation_key_count']}`",
        f"- Translation aliases: `{summary['translation_alias_count']}`",
        f"- Access fields/headers/nav labels: `{summary['access_field_count']}`",
        f"- Unmapped labels: `{summary['unmapped_label_count']}`",
        "",
        "## Safety",
        "",
        "- No credentials, cookies, tokens, HAR files, HTTP bodies, screenshots or row values are included.",
        "- Contract mappings are proposals and remain pending provider/platform validation.",
        "- Browser endpoints observed in captures are not treated as API contracts.",
        "",
        "## Login Statuses",
        "",
    ]
    for status, count in summary["login_statuses"]:
        lines.append(f"- `{status}`: {count}")
    lines.extend(["", "## Top Translation Keys", ""])
    top = sorted(catalog["translations"], key=lambda item: item["alias_count"], reverse=True)[:30]
    for item in top:
        lines.append(
            f"- `{item['standard_key']}`: {item['alias_count']} aliases across {item['platform_count']} platforms"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _platform_key(host: str, fallback: str) -> str:
    host_l = (host or "").lower()
    if host_l in HOST_TO_PLATFORM_KEY:
        return HOST_TO_PLATFORM_KEY[host_l]
    parsed = urlparse(host_l)
    netloc = parsed.netloc or host_l
    if netloc in HOST_TO_PLATFORM_KEY:
        return HOST_TO_PLATFORM_KEY[netloc]
    value = fallback or host_l or "unknown"
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    return value[:80] or "unknown"


def _redact_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"[\w.\-+]+@[\w.\-]+\.\w+", "[email]", text)
    text = re.sub(r"\b\d{8}[A-Za-z]\b", "[dni]", text)
    text = re.sub(r"\b[XYZ]\d{7}[A-Za-z]\b", "[nie]", text, flags=re.I)
    text = re.sub(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b", "[phone-or-id]", text)
    for hint in SECRET_HINTS:
        text = re.sub(rf"({hint}\s*[:=]\s*)([^\s,;]+)", r"\1[redacted]", text, flags=re.I)
    return " ".join(text.split())[:300]


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        if any(hint in key.lower() for hint in SECRET_HINTS):
            safe[key] = "[redacted]"
        elif isinstance(value, str):
            safe[key] = _redact_text(value)
        else:
            safe[key] = value
    return safe


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_redact_text(item) for item in value if _redact_text(item)]


def _first_nonempty(*values: object) -> str | None:
    for value in values:
        if value is None:
            continue
        cleaned = _redact_text(value)
        if cleaned:
            return cleaned
    return None


if __name__ == "__main__":
    main()
