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

from app.db.session import get_session_factory
from app.services.platform_edit_methods import build_platform_edit_methods


def main() -> None:
    parser = argparse.ArgumentParser(description="Build platform/company field edit method catalog.")
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--company-id", type=int, default=None)
    parser.add_argument("--priority-group", default="all")
    parser.add_argument("--seed", action="store_true", help="Inicializa/actualiza datos demo antes de generar catalogo.")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "artifacts" / "platform-edit-methods")
    args = parser.parse_args()

    if args.seed:
        from app.db.demo_seed import create_demo_database

        create_demo_database()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with get_session_factory()() as session:
        catalog = build_platform_edit_methods(
            session,
            tenant_id=args.tenant_id,
            company_id=args.company_id,
            priority_group=args.priority_group,
        )

    _write_json(args.out_dir / "platform_field_edit_methods.redacted.json", catalog)
    _write_csv(args.out_dir / "platform_field_edit_methods.redacted.csv", _field_rows(catalog))
    _write_csv(args.out_dir / "platform_edit_operations.redacted.csv", _operation_rows(catalog))
    _write_markdown(args.out_dir / "platform_field_edit_summary.redacted.md", catalog)

    print(
        json.dumps(
            {
                "platforms": catalog["totals"]["platforms"],
                "contexts": catalog["totals"]["contexts"],
                "field_methods": catalog["totals"]["field_methods"],
                "ready_for_preview": catalog["totals"]["ready_for_preview"],
                "needs_editable_capture": catalog["totals"]["needs_editable_capture"],
                "needs_mapping_review": catalog["totals"]["needs_mapping_review"],
                "needs_mapping": catalog["totals"]["needs_mapping"],
                "operations_ready_for_preview": catalog["totals"]["operations_ready_for_preview"],
                "out_dir": str(args.out_dir.relative_to(ROOT)),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def _field_rows(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for context in catalog.get("contexts") or []:
        for field in context.get("field_methods") or []:
            evidence = field.get("evidence_summary") or {}
            rows.append(
                {
                    "platform_slug": context.get("platform_slug"),
                    "platform_name": context.get("platform_name"),
                    "account_proposal_id": context.get("account_proposal_id"),
                    "trace_label": context.get("trace_label"),
                    "external_company_name": context.get("external_company_name"),
                    "standard_key": field.get("standard_key"),
                    "display_name": field.get("display_name"),
                    "entity_scope": field.get("entity_scope"),
                    "data_type": field.get("data_type"),
                    "status": field.get("status"),
                    "method": field.get("method"),
                    "selector_policy": field.get("selector_policy"),
                    "requires_preview": field.get("requires_preview"),
                    "requires_manual_approval": field.get("requires_manual_approval"),
                    "requires_before_after_audit": field.get("requires_before_after_audit"),
                    "sensitive": field.get("sensitive"),
                    "observed_label_count": evidence.get("observed_label_count"),
                    "editable_label_count": evidence.get("editable_label_count"),
                    "mapping_count": evidence.get("mapping_count"),
                    "mapping_review_statuses": ", ".join(evidence.get("mapping_review_statuses") or []),
                    "next_action": field.get("next_action"),
                }
            )
    return rows


def _operation_rows(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for context in catalog.get("contexts") or []:
        for operation in context.get("operations") or []:
            rows.append(
                {
                    "platform_slug": context.get("platform_slug"),
                    "platform_name": context.get("platform_name"),
                    "account_proposal_id": context.get("account_proposal_id"),
                    "trace_label": context.get("trace_label"),
                    "external_company_name": context.get("external_company_name"),
                    "operation": operation.get("operation"),
                    "status": operation.get("status"),
                    "required_standard_keys": ", ".join(operation.get("required_standard_keys") or []),
                    "ready_keys": ", ".join(operation.get("ready_keys") or []),
                    "missing_or_unreviewed_keys": ", ".join(operation.get("missing_or_unreviewed_keys") or []),
                    "needs_editable_capture_keys": ", ".join(
                        operation.get("needs_editable_capture_keys") or []
                    ),
                    "next_action": operation.get("next_action"),
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


def _write_markdown(path: Path, catalog: dict[str, Any]) -> None:
    totals = catalog["totals"]
    lines = [
        "# Platform Field Edit Methods",
        "",
        "Catalogo operativo por plataforma y empresa externa, generado desde capturas redaccionadas y mapeos revisables.",
        "",
        "## Politica",
        "",
        "- Escrituras externas: requieren preview, autorizacion y auditoria antes/despues.",
        "- Captcha/MFA: validacion humana en navegador visible, sin bypass.",
        "- Selectores comerciales: no se guardan selectores estaticos inventados.",
        "- Resolucion de campos: por etiqueta observada o nombre estable en tiempo de ejecucion.",
        "",
        "## Resumen",
        "",
        f"- Plataformas: `{totals['platforms']}`",
        f"- Contextos plataforma/empresa: `{totals['contexts']}`",
        f"- Metodos de campo: `{totals['field_methods']}`",
        f"- Campos listos para preview: `{totals['ready_for_preview']}`",
        f"- Campos que requieren captura editable: `{totals['needs_editable_capture']}`",
        f"- Campos que requieren revisar mapeo: `{totals['needs_mapping_review']}`",
        f"- Campos sin mapeo: `{totals['needs_mapping']}`",
        f"- Operaciones listas para preview: `{totals['operations_ready_for_preview']}`",
        "",
        "## Contextos",
        "",
    ]
    for context in catalog.get("contexts") or []:
        status_counts: dict[str, int] = {}
        for field in context.get("field_methods") or []:
            status = str(field.get("status"))
            status_counts[status] = status_counts.get(status, 0) + 1
        operation_counts: dict[str, int] = {}
        for operation in context.get("operations") or []:
            status = str(operation.get("status"))
            operation_counts[status] = operation_counts.get(status, 0) + 1
        lines.extend(
            [
                f"### {context['trace_label']}",
                "",
                f"- Host: `{context.get('host') or 'pending'}`",
                f"- Cuenta externa: `{context.get('external_company_name') or 'sin cuenta especifica'}`",
                f"- Campos por estado: `{_format_counts(status_counts)}`",
                f"- Operaciones por estado: `{_format_counts(operation_counts)}`",
                "",
                "| Campo | Metodo | Estado | Accion siguiente |",
                "| --- | --- | --- | --- |",
            ]
        )
        visible_fields = [
            field
            for field in context.get("field_methods") or []
            if field.get("status") != "not_external_edit_target"
        ]
        for field in visible_fields:
            lines.append(
                "| "
                f"{field['standard_key']} | "
                f"{field['method']} | "
                f"{field['status']} | "
                f"{field['next_action']} |"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _format_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{key}: {value}" for key, value in sorted(counts.items())) or "none"


if __name__ == "__main__":
    main()
