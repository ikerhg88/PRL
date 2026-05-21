from __future__ import annotations

# ruff: noqa: E402

import argparse
import csv
import html
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
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

from app.db.demo_seed import create_demo_database
from app.db.models import (
    Company,
    ExternalDocumentStatus,
    ExternalPlatform,
    PlatformDiscoveredLabel,
    PlatformRpaAccountProposal,
    PlatformRpaManifest,
    PlatformRpaMappingProposal,
    PlatformStructureSnapshot,
    Worker,
    WorkerPlatformRegistration,
)
from app.db.session import get_session_factory
from app.services.platform_data_coverage import CANONICAL_KEY_ALIASES
from app.services.platform_mapping import STANDARD_LABELS_BY_KEY


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a platform obtained-data and field correspondence report."
    )
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--company-id", type=int, default=None)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "artifacts" / "platform-obtained-mapping")
    parser.add_argument("--no-pdf", action="store_true")
    args = parser.parse_args()

    create_demo_database()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = args.out_dir / f"platform_obtained_data_mapping_{timestamp}"

    with get_session_factory()() as session:
        payload = build_payload(session, tenant_id=args.tenant_id, company_id=args.company_id)

    json_path = base.with_suffix(".json")
    html_path = base.with_suffix(".html")
    pdf_path = base.with_suffix(".pdf")
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    html_path.write_text(render_html(payload), encoding="utf-8")

    latest_json = args.out_dir / "platform_obtained_data_mapping_latest.json"
    latest_html = args.out_dir / "platform_obtained_data_mapping_latest.html"
    latest_pdf = args.out_dir / "platform_obtained_data_mapping_latest.pdf"
    latest_json.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_html.write_text(html_path.read_text(encoding="utf-8"), encoding="utf-8")

    _write_csv(args.out_dir / "platform_obtained_data_index.redacted.csv", _obtained_index_rows(payload))
    correspondence_rows = _correspondence_rows(payload)
    _write_csv(args.out_dir / "platform_field_correspondences.redacted.csv", correspondence_rows)
    _write_csv(
        args.out_dir / "platform_field_correspondences_mapped.redacted.csv",
        [row for row in correspondence_rows if row.get("internal_key")],
    )
    _write_csv(args.out_dir / "platform_external_statuses.redacted.csv", _external_status_rows(payload))

    if not args.no_pdf:
        render_pdf(html_path, pdf_path)
        latest_pdf.write_bytes(pdf_path.read_bytes())

    print(f"JSON: {json_path}")
    print(f"JSON_LATEST: {latest_json}")
    print(f"HTML: {html_path}")
    print(f"HTML_LATEST: {latest_html}")
    if pdf_path.exists():
        print(f"PDF: {pdf_path}")
        print(f"PDF_LATEST: {latest_pdf}")
    print(
        json.dumps(
            {
                "platform_contexts": len(payload["contexts"]),
                "snapshots": payload["summary"]["snapshot_count"],
                "captured_labels": payload["summary"]["captured_label_count"],
                "mapping_correspondences": payload["summary"]["mapping_count"],
                "worker_platform_observations": payload["summary"]["worker_platform_observation_count"],
                "external_document_statuses": payload["summary"]["external_document_status_count"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def build_payload(session: Any, *, tenant_id: int, company_id: int | None) -> dict[str, Any]:
    company = _company(session, tenant_id=tenant_id, company_id=company_id)
    platforms = {
        platform.id: platform
        for platform in session.scalars(select(ExternalPlatform).order_by(ExternalPlatform.name))
        if platform.platform_key != "mock_cae"
    }
    manifests = [
        manifest
        for manifest in session.scalars(
            select(PlatformRpaManifest)
            .where(PlatformRpaManifest.tenant_id == tenant_id)
            .order_by(PlatformRpaManifest.platform_name)
        )
        if manifest.external_platform_id in platforms
    ]
    accounts = list(
        session.scalars(
            select(PlatformRpaAccountProposal)
            .where(PlatformRpaAccountProposal.tenant_id == tenant_id)
            .order_by(PlatformRpaAccountProposal.manifest_id, PlatformRpaAccountProposal.external_company_name)
        )
    )
    snapshots = [
        snapshot
        for snapshot in session.scalars(
            select(PlatformStructureSnapshot)
            .where(PlatformStructureSnapshot.tenant_id == tenant_id)
            .order_by(PlatformStructureSnapshot.platform_label, PlatformStructureSnapshot.id)
        )
        if snapshot.external_platform_id in platforms or not snapshot.external_platform_id
    ]
    labels = list(
        session.scalars(
            select(PlatformDiscoveredLabel)
            .where(PlatformDiscoveredLabel.tenant_id == tenant_id)
            .order_by(
                PlatformDiscoveredLabel.snapshot_id,
                PlatformDiscoveredLabel.standard_key,
                PlatformDiscoveredLabel.raw_label,
            )
        )
    )
    mappings = list(
        session.scalars(
            select(PlatformRpaMappingProposal)
            .where(PlatformRpaMappingProposal.tenant_id == tenant_id)
            .order_by(
                PlatformRpaMappingProposal.manifest_id,
                PlatformRpaMappingProposal.mapping_kind,
                PlatformRpaMappingProposal.iker_key,
            )
        )
    )
    workers = {
        worker.id: worker
        for worker in session.scalars(select(Worker).where(Worker.tenant_id == tenant_id))
    }
    observations = [
        row
        for row in session.scalars(
            select(WorkerPlatformRegistration)
            .where(WorkerPlatformRegistration.tenant_id == tenant_id)
            .order_by(WorkerPlatformRegistration.platform_name, WorkerPlatformRegistration.worker_id)
        )
        if row.source != "connector_demo"
    ]
    external_statuses = [
        status
        for status in session.scalars(
            select(ExternalDocumentStatus)
            .where(ExternalDocumentStatus.tenant_id == tenant_id)
            .order_by(ExternalDocumentStatus.last_checked_at.desc(), ExternalDocumentStatus.id.desc())
        )
        if status.external_platform_id in platforms
    ]

    accounts_by_manifest = _accounts_by_manifest(accounts)
    snapshots_by_context = _snapshots_by_context(manifests, accounts, snapshots)
    labels_by_snapshot = _labels_by_snapshot(labels)
    mappings_by_manifest = _mappings_by_manifest(mappings)
    observations_by_platform = _observations_by_platform(observations)
    statuses_by_platform = _statuses_by_platform(external_statuses)
    contexts = []
    for manifest in manifests:
        for account in accounts_by_manifest.get(manifest.id) or [None]:
            key = (manifest.id, account.id if account else None)
            context_snapshots = snapshots_by_context.get(key, [])
            context_labels = [
                label
                for snapshot in context_snapshots
                for label in labels_by_snapshot.get(snapshot.id, [])
            ]
            context = {
                "manifest_id": manifest.id,
                "platform_slug": manifest.platform_slug,
                "platform_name": manifest.platform_name,
                "external_platform_id": manifest.external_platform_id,
                "external_company_name": account.external_company_name if account else None,
                "account_proposal_id": account.id if account else None,
                "host": account.host if account and account.host else (manifest.hosts[0] if manifest.hosts else None),
                "entry_url": account.entry_url if account else (manifest.entry_urls[0] if manifest.entry_urls else None),
                "snapshots": [_snapshot_payload(snapshot) for snapshot in context_snapshots],
                "captured_field_correspondences": [
                    _label_payload(label, snapshot_by_id={snapshot.id: snapshot for snapshot in context_snapshots})
                    for label in context_labels
                ],
                "mapping_correspondences": [
                    _mapping_payload(mapping) for mapping in mappings_by_manifest.get(manifest.id, [])
                ],
                "worker_platform_observations": [
                    _observation_payload(observation, workers)
                    for observation in observations_by_platform.get(manifest.external_platform_id or -1, [])
                ],
                "external_document_statuses": [
                    _status_payload(status) for status in statuses_by_platform.get(manifest.external_platform_id or -1, [])
                ],
            }
            contexts.append(context)

    return {
        "generated_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "tenant_id": tenant_id,
        "company": {
            "id": company.id if company else None,
            "name": company.name if company else "ARM",
            "tax_id": company.tax_id if company else None,
        },
        "summary": {
            "platform_context_count": len(contexts),
            "snapshot_count": sum(len(context["snapshots"]) for context in contexts),
            "captured_label_count": sum(
                len(context["captured_field_correspondences"]) for context in contexts
            ),
            "mapping_count": sum(len(context["mapping_correspondences"]) for context in contexts),
            "worker_platform_observation_count": sum(
                len(context["worker_platform_observations"]) for context in contexts
            ),
            "external_document_status_count": sum(
                len(context["external_document_statuses"]) for context in contexts
            ),
        },
        "contexts": contexts,
    }


def _company(session: Any, *, tenant_id: int, company_id: int | None) -> Company | None:
    statement = select(Company).where(Company.tenant_id == tenant_id)
    if company_id is not None:
        statement = statement.where(Company.id == company_id)
    else:
        statement = statement.where(Company.name.ilike("ARM%"))
    return session.scalars(statement.order_by(Company.id)).first()


def _accounts_by_manifest(
    accounts: list[PlatformRpaAccountProposal],
) -> dict[int, list[PlatformRpaAccountProposal]]:
    result: dict[int, list[PlatformRpaAccountProposal]] = defaultdict(list)
    for account in accounts:
        result[account.manifest_id].append(account)
    return result


def _labels_by_snapshot(
    labels: list[PlatformDiscoveredLabel],
) -> dict[int, list[PlatformDiscoveredLabel]]:
    result: dict[int, list[PlatformDiscoveredLabel]] = defaultdict(list)
    for label in labels:
        result[label.snapshot_id].append(label)
    return result


def _mappings_by_manifest(
    mappings: list[PlatformRpaMappingProposal],
) -> dict[int, list[PlatformRpaMappingProposal]]:
    result: dict[int, list[PlatformRpaMappingProposal]] = defaultdict(list)
    for mapping in mappings:
        result[mapping.manifest_id].append(mapping)
    return result


def _observations_by_platform(
    observations: list[WorkerPlatformRegistration],
) -> dict[int, list[WorkerPlatformRegistration]]:
    result: dict[int, list[WorkerPlatformRegistration]] = defaultdict(list)
    for observation in observations:
        if observation.external_platform_id is not None:
            result[observation.external_platform_id].append(observation)
    return result


def _statuses_by_platform(
    statuses: list[ExternalDocumentStatus],
) -> dict[int, list[ExternalDocumentStatus]]:
    result: dict[int, list[ExternalDocumentStatus]] = defaultdict(list)
    for status in statuses:
        result[status.external_platform_id].append(status)
    return result


def _snapshots_by_context(
    manifests: list[PlatformRpaManifest],
    accounts: list[PlatformRpaAccountProposal],
    snapshots: list[PlatformStructureSnapshot],
) -> dict[tuple[int, int | None], list[PlatformStructureSnapshot]]:
    result: dict[tuple[int, int | None], list[PlatformStructureSnapshot]] = defaultdict(list)
    for manifest in manifests:
        related_accounts = [account for account in accounts if account.manifest_id == manifest.id] or [None]
        for account in related_accounts:
            key = (manifest.id, account.id if account else None)
            hosts = {normalize_host(host) for host in manifest.hosts or []}
            if account and account.host:
                hosts.add(normalize_host(account.host))
            label_terms = {manifest.platform_name.lower(), manifest.platform_slug.lower()}
            if account and account.external_company_name:
                label_terms.update(part.strip().lower() for part in account.external_company_name.split(",") if part.strip())
            for snapshot in snapshots:
                snapshot_host = normalize_host(snapshot.host)
                snapshot_label = (snapshot.platform_label or "").lower()
                if snapshot.external_platform_id and snapshot.external_platform_id == manifest.external_platform_id:
                    result[key].append(snapshot)
                elif snapshot_host and snapshot_host in hosts:
                    result[key].append(snapshot)
                elif any(term and term in snapshot_label for term in label_terms):
                    result[key].append(snapshot)
    return {key: dedupe_snapshots(value) for key, value in result.items()}


def normalize_host(value: str | None) -> str:
    if not value:
        return ""
    return value.lower().replace("https://", "").replace("http://", "").split("/", 1)[0]


def dedupe_snapshots(rows: list[PlatformStructureSnapshot]) -> list[PlatformStructureSnapshot]:
    seen: set[int] = set()
    result: list[PlatformStructureSnapshot] = []
    for row in rows:
        if row.id in seen:
            continue
        seen.add(row.id)
        result.append(row)
    return result


def _snapshot_payload(snapshot: PlatformStructureSnapshot) -> dict[str, Any]:
    pages = snapshot.structure_json.get("pages") if isinstance(snapshot.structure_json, dict) else []
    page_count = len(pages) if isinstance(pages, list) else 0
    return {
        "id": snapshot.id,
        "platform_label": snapshot.platform_label,
        "host": snapshot.host,
        "login_status": snapshot.login_status,
        "source_type": snapshot.source_type,
        "source_ref": snapshot.source_ref,
        "status": snapshot.status,
        "page_count": page_count,
        "summary": _safe_summary(snapshot.summary_json),
        "pages": [_page_payload(page) for page in pages[:20]] if isinstance(pages, list) else [],
    }


def _page_payload(page: Any) -> dict[str, Any]:
    if not isinstance(page, dict):
        return {}
    return {
        "label": page.get("label"),
        "title": page.get("title"),
        "headings": _safe_list(page.get("headings")),
        "nav_labels": _safe_list(page.get("nav_labels") or page.get("navigation_labels")),
        "table_headers": _safe_table_headers(page.get("table_headers")),
        "grid_headers": _safe_list(page.get("grid_headers")),
        "forms": _forms_payload(page.get("forms")),
        "status_counts": page.get("status_counts") if isinstance(page.get("status_counts"), list) else [],
    }


def _forms_payload(forms: Any) -> list[dict[str, Any]]:
    if not isinstance(forms, list):
        return []
    result = []
    for form in forms[:10]:
        if not isinstance(form, dict):
            continue
        result.append(
            {
                "method": form.get("method"),
                "action": form.get("action"),
                "input_count": len(form.get("inputs") or []) if isinstance(form.get("inputs"), list) else 0,
                "button_count": len(form.get("buttons") or []) if isinstance(form.get("buttons"), list) else 0,
            }
        )
    return result


def _label_payload(label: PlatformDiscoveredLabel, *, snapshot_by_id: dict[int, PlatformStructureSnapshot]) -> dict[str, Any]:
    standard = STANDARD_LABELS_BY_KEY.get(label.standard_key or "")
    snapshot = snapshot_by_id.get(label.snapshot_id)
    return {
        "source": "captured_label",
        "snapshot_id": label.snapshot_id,
        "snapshot_label": snapshot.platform_label if snapshot else None,
        "host": snapshot.host if snapshot else None,
        "page_label": label.page_label,
        "external_label": label.raw_label,
        "label_kind": label.label_kind,
        "entity_scope": label.entity_scope,
        "standard_key": label.standard_key,
        "standard_display": standard.display_name if standard else None,
        "confidence": label.confidence,
        "review_status": label.review_status,
    }


def _mapping_payload(mapping: PlatformRpaMappingProposal) -> dict[str, Any]:
    canonical_key = _canonical_key(mapping.iker_key, mapping.mapping_kind)
    standard = STANDARD_LABELS_BY_KEY.get(canonical_key or "")
    return {
        "source": "contract_mapping",
        "mapping_id": mapping.id,
        "mapping_kind": mapping.mapping_kind,
        "entity_scope": mapping.entity_scope,
        "internal_key": mapping.iker_key,
        "canonical_key": canonical_key,
        "standard_display": standard.display_name if standard else None,
        "external_label": mapping.external_label,
        "external_catalog_value": mapping.external_catalog_value,
        "requirement": mapping.requirement,
        "applies_to": mapping.applies_to,
        "review_status": mapping.review_status,
        "status": mapping.status,
    }


def _observation_payload(observation: WorkerPlatformRegistration, workers: dict[int, Worker]) -> dict[str, Any]:
    worker = workers.get(observation.worker_id)
    return {
        "platform_name": observation.platform_name,
        "assignment_scope": observation.assignment_scope,
        "worker_id": observation.worker_id,
        "worker_name": f"{worker.first_name} {worker.last_name}" if worker else None,
        "external_worker_id": observation.external_worker_id,
        "registration_status": observation.registration_status,
        "source": observation.source,
        "last_synced_at": observation.last_synced_at.isoformat() if observation.last_synced_at else None,
        "notes": observation.notes,
    }


def _status_payload(status: ExternalDocumentStatus) -> dict[str, Any]:
    return {
        "id": status.id,
        "document_version_id": status.document_version_id,
        "external_document_id": status.external_document_id,
        "external_requirement_id": status.external_requirement_id,
        "status": status.status,
        "external_comment": status.external_comment,
        "last_checked_at": status.last_checked_at.isoformat() if status.last_checked_at else None,
    }


def _canonical_key(value: str | None, mapping_kind: str | None = None) -> str | None:
    if not value:
        return "document.type" if mapping_kind == "document_type" else None
    cleaned = value.strip()
    if mapping_kind == "document_type":
        return "document.type"
    if cleaned in STANDARD_LABELS_BY_KEY:
        return cleaned
    return CANONICAL_KEY_ALIASES.get(cleaned)


def _safe_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if key in {"page_count", "pages_captured", "host", "login_status", "captcha_detected", "mfa_detected", "platform_key", "row"}
    }


def _safe_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value[:30] if str(item).strip()]


def _safe_table_headers(value: Any) -> list[list[str]]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:12]:
        if isinstance(item, list):
            result.append([str(entry) for entry in item[:30] if str(entry).strip()])
    return result


def render_html(payload: dict[str, Any]) -> str:
    style = """
      @page { size: A4 landscape; margin: 9mm; }
      * { box-sizing: border-box; }
      body { color: #101828; font-family: Arial, sans-serif; font-size: 8.8px; }
      h1 { font-size: 19px; margin: 0 0 4px; }
      h2 { font-size: 14px; margin: 13px 0 6px; page-break-after: avoid; }
      h3 { font-size: 11.5px; margin: 10px 0 5px; page-break-after: avoid; }
      p { margin: 3px 0; }
      table { border-collapse: collapse; margin: 5px 0 10px; width: 100%; }
      th, td { border: 1px solid #d0d7e2; padding: 3.5px; vertical-align: top; }
      th { background: #eef3f8; font-weight: 700; text-align: left; }
      tr { page-break-inside: avoid; }
      .box { border: 1px solid #d0d7e2; border-radius: 4px; margin: 6px 0; padding: 6px; }
      .muted, .small { color: #52627a; }
      .small { font-size: 7.8px; }
      .mono { font-family: Consolas, monospace; }
      .page-break { page-break-before: always; }
      .label-cell { word-break: break-word; }
    """
    summary = payload["summary"]
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <title>Datos obtenidos y correspondencias por plataforma</title>
  <style>{style}</style>
</head>
<body>
  <h1>Datos obtenidos y correspondencias por plataforma</h1>
  <p class="muted">Generado: {esc(payload["generated_at"])} | Empresa: {esc(payload["company"]["name"])}</p>
  <div class="box">
    Este informe consolida informacion obtenida o registrada en el Hub desde plataformas externas:
    contextos, capturas redaccionadas, etiquetas visibles, estados externos y correspondencias de campos.
  </div>
  <div class="box">
    Contextos: {summary["platform_context_count"]} |
    Capturas: {summary["snapshot_count"]} |
    Etiquetas detectadas: {summary["captured_label_count"]} |
    Correspondencias de mapeo: {summary["mapping_count"]} |
    Observaciones trabajador/plataforma: {summary["worker_platform_observation_count"]} |
    Estados documentales externos: {summary["external_document_status_count"]}
  </div>
  {render_context_summary(payload)}
  {render_context_sections(payload)}
</body>
</html>"""


def render_context_summary(payload: dict[str, Any]) -> str:
    rows = []
    for context in payload["contexts"]:
        rows.append(
            f"""
            <tr>
              <td><strong>{esc(context["platform_name"])}</strong><br><span class="small">{esc(context["platform_slug"])}</span></td>
              <td>{esc(context.get("external_company_name") or "")}</td>
              <td>{esc(context.get("host") or "")}</td>
              <td>{len(context["snapshots"])}</td>
              <td>{len(context["captured_field_correspondences"])}</td>
              <td>{len(context["mapping_correspondences"])}</td>
              <td>{len(context["worker_platform_observations"])}</td>
              <td>{len(context["external_document_statuses"])}</td>
            </tr>
            """
        )
    return f"""
    <h2>Resumen por plataforma y empresa externa</h2>
    <table>
      <thead><tr><th>Plataforma</th><th>Empresa/contexto externo</th><th>Host</th><th>Capturas</th><th>Etiquetas</th><th>Mapeos</th><th>Trabajadores</th><th>Estados ext.</th></tr></thead>
      <tbody>{"".join(rows) or empty_row(8)}</tbody>
    </table>
    """


def render_context_sections(payload: dict[str, Any]) -> str:
    sections = []
    for index, context in enumerate(payload["contexts"], start=1):
        sections.append(
            f"""
            <h2 class="{ 'page-break' if index > 1 else '' }">{esc(context["platform_name"])} / {esc(context.get("external_company_name") or "")}</h2>
            <p class="small">Host: {esc(context.get("host") or "")} | Entrada registrada: <span class="mono">{esc(context.get("entry_url") or "")}</span></p>
            {render_snapshots_table(context)}
            {render_captured_correspondence_table(context)}
            {render_mapping_correspondence_table(context)}
            {render_observations_table(context)}
            {render_external_status_table(context)}
            """
        )
    return "".join(sections)


def render_snapshots_table(context: dict[str, Any]) -> str:
    rows = []
    for snapshot in context["snapshots"]:
        pages = "<br>".join(
            f"- {esc(page.get('label') or page.get('title') or '')}: {esc(', '.join(page.get('headings') or [])[:220])}"
            for page in snapshot.get("pages", [])[:8]
        )
        rows.append(
            f"""
            <tr>
              <td>#{snapshot["id"]}</td>
              <td>{esc(snapshot["platform_label"])}</td>
              <td>{esc(snapshot.get("host") or "")}</td>
              <td>{esc(snapshot.get("login_status") or "")}</td>
              <td>{snapshot.get("page_count") or 0}</td>
              <td>{esc(snapshot.get("source_ref") or "")}</td>
              <td>{pages}</td>
            </tr>
            """
        )
    return f"""
    <h3>Datos obtenidos: capturas redaccionadas</h3>
    <table>
      <thead><tr><th>ID</th><th>Etiqueta</th><th>Host</th><th>Estado observado</th><th>Paginas</th><th>Fuente</th><th>Paginas/cabeceras visibles</th></tr></thead>
      <tbody>{"".join(rows) or empty_row(7)}</tbody>
    </table>
    """


def render_captured_correspondence_table(context: dict[str, Any]) -> str:
    rows = []
    for item in context["captured_field_correspondences"]:
        if not item.get("standard_key"):
            continue
        rows.append(
            f"""
            <tr>
              <td>{esc(item.get("page_label") or "")}</td>
              <td>{esc(item.get("label_kind") or "")}</td>
              <td class="label-cell">{esc(item.get("external_label") or "")}</td>
              <td class="mono">{esc(item.get("standard_key") or "")}</td>
              <td>{esc(item.get("standard_display") or "")}</td>
              <td>{esc(item.get("confidence") or "")}</td>
              <td>{esc(item.get("review_status") or "")}</td>
            </tr>
            """
        )
    return f"""
    <h3>Correspondencias desde etiquetas capturadas</h3>
    <table>
      <thead><tr><th>Pagina</th><th>Tipo</th><th>Campo/etiqueta externa</th><th>Campo interno</th><th>Nombre interno</th><th>Conf.</th><th>Revision</th></tr></thead>
      <tbody>{"".join(rows) or empty_row(7)}</tbody>
    </table>
    """


def render_mapping_correspondence_table(context: dict[str, Any]) -> str:
    rows = []
    for item in context["mapping_correspondences"]:
        rows.append(
            f"""
            <tr>
              <td>{esc(item.get("mapping_kind") or "")}</td>
              <td class="label-cell">{esc(item.get("external_label") or item.get("external_catalog_value") or item.get("requirement") or "")}</td>
              <td>{esc(item.get("applies_to") or "")}</td>
              <td class="mono">{esc(item.get("canonical_key") or item.get("internal_key") or "")}</td>
              <td>{esc(item.get("standard_display") or "")}</td>
              <td>{esc(item.get("review_status") or "")}</td>
            </tr>
            """
        )
    return f"""
    <h3>Correspondencias desde mapeos importados</h3>
    <table>
      <thead><tr><th>Tipo mapeo</th><th>Campo/requisito externo</th><th>Aplica a</th><th>Campo interno</th><th>Nombre interno</th><th>Revision</th></tr></thead>
      <tbody>{"".join(rows) or empty_row(6)}</tbody>
    </table>
    """


def render_observations_table(context: dict[str, Any]) -> str:
    rows = []
    for item in context["worker_platform_observations"]:
        rows.append(
            f"""
            <tr>
              <td>{esc(item.get("worker_name") or "")}</td>
              <td>{esc(item.get("assignment_scope") or "")}</td>
              <td>{esc(item.get("registration_status") or "")}</td>
              <td>{esc(item.get("external_worker_id") or "")}</td>
              <td>{esc(item.get("last_synced_at") or "")}</td>
              <td>{esc(item.get("notes") or "")}</td>
            </tr>
            """
        )
    return f"""
    <h3>Observaciones de trabajadores registradas</h3>
    <table>
      <thead><tr><th>Trabajador</th><th>Contexto</th><th>Estado observado</th><th>ID externo</th><th>Fecha</th><th>Nota</th></tr></thead>
      <tbody>{"".join(rows) or empty_row(6)}</tbody>
    </table>
    """


def render_external_status_table(context: dict[str, Any]) -> str:
    rows = []
    for item in context["external_document_statuses"]:
        rows.append(
            f"""
            <tr>
              <td>{esc(item.get("document_version_id") or "")}</td>
              <td>{esc(item.get("external_document_id") or "")}</td>
              <td>{esc(item.get("external_requirement_id") or "")}</td>
              <td>{esc(item.get("status") or "")}</td>
              <td>{esc(item.get("external_comment") or "")}</td>
              <td>{esc(item.get("last_checked_at") or "")}</td>
            </tr>
            """
        )
    return f"""
    <h3>Estados documentales externos registrados</h3>
    <table>
      <thead><tr><th>Version doc.</th><th>ID doc. externo</th><th>Requisito externo</th><th>Estado</th><th>Comentario externo</th><th>Fecha lectura</th></tr></thead>
      <tbody>{"".join(rows) or empty_row(6)}</tbody>
    </table>
    """


def _obtained_index_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for context in payload["contexts"]:
        for snapshot in context["snapshots"]:
            rows.append(
                {
                    "platform_slug": context["platform_slug"],
                    "platform_name": context["platform_name"],
                    "external_company_name": context.get("external_company_name"),
                    "snapshot_id": snapshot["id"],
                    "snapshot_label": snapshot["platform_label"],
                    "host": snapshot.get("host"),
                    "login_status": snapshot.get("login_status"),
                    "page_count": snapshot.get("page_count"),
                    "source_ref": snapshot.get("source_ref"),
                }
            )
    return rows


def _correspondence_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for context in payload["contexts"]:
        for item in context["captured_field_correspondences"]:
            rows.append(
                {
                    "platform_slug": context["platform_slug"],
                    "platform_name": context["platform_name"],
                    "external_company_name": context.get("external_company_name"),
                    "source": "captured_label",
                    "page_label": item.get("page_label"),
                    "label_kind": item.get("label_kind"),
                    "external_label": item.get("external_label"),
                    "internal_key": item.get("standard_key"),
                    "internal_display": item.get("standard_display"),
                    "review_status": item.get("review_status"),
                    "confidence": item.get("confidence"),
                }
            )
        for item in context["mapping_correspondences"]:
            rows.append(
                {
                    "platform_slug": context["platform_slug"],
                    "platform_name": context["platform_name"],
                    "external_company_name": context.get("external_company_name"),
                    "source": "contract_mapping",
                    "page_label": "",
                    "label_kind": item.get("mapping_kind"),
                    "external_label": item.get("external_label") or item.get("external_catalog_value") or item.get("requirement"),
                    "internal_key": item.get("canonical_key") or item.get("internal_key"),
                    "internal_display": item.get("standard_display"),
                    "review_status": item.get("review_status"),
                    "confidence": "",
                }
            )
    return rows


def _external_status_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for context in payload["contexts"]:
        for item in context["external_document_statuses"]:
            rows.append(
                {
                    "platform_slug": context["platform_slug"],
                    "platform_name": context["platform_name"],
                    "external_company_name": context.get("external_company_name"),
                    "document_version_id": item.get("document_version_id"),
                    "external_document_id": item.get("external_document_id"),
                    "external_requirement_id": item.get("external_requirement_id"),
                    "status": item.get("status"),
                    "external_comment": item.get("external_comment"),
                    "last_checked_at": item.get("last_checked_at"),
                }
            )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if fieldnames:
            writer.writeheader()
        writer.writerows(rows)


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def empty_row(columns: int) -> str:
    return f"<tr><td colspan=\"{columns}\">Sin datos registrados.</td></tr>"


def render_pdf(html_path: Path, pdf_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = None
        launch_attempts: list[dict[str, Any]] = [{"channel": "chrome"}, {"channel": "msedge"}]
        for executable in [
            Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        ]:
            if executable.exists():
                launch_attempts.append({"executable_path": str(executable)})
        last_error: Exception | None = None
        for attempt in launch_attempts:
            try:
                browser = playwright.chromium.launch(**attempt)
                break
            except Exception as exc:  # pragma: no cover - depends on local browser installation.
                last_error = exc
        if browser is None:
            raise RuntimeError(f"Could not launch a browser to render PDF: {last_error}")
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto(html_path.as_uri(), wait_until="load")
        page.pdf(path=str(pdf_path), format="A4", landscape=True, print_background=True)
        browser.close()


if __name__ == "__main__":
    main()
