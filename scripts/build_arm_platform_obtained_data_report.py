from __future__ import annotations

# ruff: noqa: E402

import argparse
import html
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
    PlatformDiscoveredLabel,
    PlatformReviewRun,
    PlatformRpaAccountProposal,
    PlatformRpaManifest,
    PlatformStructureSnapshot,
    Worker,
    WorkerPlatformRegistration,
)
from app.db.session import get_session_factory


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ARM platform obtained-data-only PDF.")
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--company-id", type=int, default=None)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "artifacts" / "admin-validation")
    parser.add_argument("--no-pdf", action="store_true")
    args = parser.parse_args()

    create_demo_database()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base_path = args.out_dir / f"arm_platform_obtained_data_{timestamp}"

    with get_session_factory()() as session:
        payload = build_payload(session, tenant_id=args.tenant_id, company_id=args.company_id)

    html_path = base_path.with_suffix(".html")
    html_path.write_text(render_html(payload), encoding="utf-8")
    latest_html = args.out_dir / "arm_platform_obtained_data_latest.html"
    latest_html.write_text(html_path.read_text(encoding="utf-8"), encoding="utf-8")

    pdf_path = base_path.with_suffix(".pdf")
    latest_pdf = args.out_dir / "arm_platform_obtained_data_latest.pdf"
    if not args.no_pdf:
        render_pdf(html_path, pdf_path)
        latest_pdf.write_bytes(pdf_path.read_bytes())

    print(f"HTML: {html_path}")
    print(f"HTML_LATEST: {latest_html}")
    if pdf_path.exists():
        print(f"PDF: {pdf_path}")
        print(f"PDF_LATEST: {latest_pdf}")


def build_payload(session: Any, *, tenant_id: int, company_id: int | None) -> dict[str, Any]:
    company = _company(session, tenant_id=tenant_id, company_id=company_id)
    manifests = list(
        session.scalars(
            select(PlatformRpaManifest)
            .where(PlatformRpaManifest.tenant_id == tenant_id)
            .order_by(PlatformRpaManifest.platform_name),
        ),
    )
    accounts = list(
        session.scalars(
            select(PlatformRpaAccountProposal)
            .where(PlatformRpaAccountProposal.tenant_id == tenant_id)
            .order_by(PlatformRpaAccountProposal.manifest_id, PlatformRpaAccountProposal.external_company_name),
        ),
    )
    snapshots = list(
        session.scalars(
            select(PlatformStructureSnapshot)
            .where(PlatformStructureSnapshot.tenant_id == tenant_id)
            .order_by(PlatformStructureSnapshot.platform_label, PlatformStructureSnapshot.id),
        ),
    )
    labels = list(
        session.scalars(
            select(PlatformDiscoveredLabel)
            .where(PlatformDiscoveredLabel.tenant_id == tenant_id)
            .order_by(PlatformDiscoveredLabel.snapshot_id, PlatformDiscoveredLabel.label_kind, PlatformDiscoveredLabel.raw_label),
        ),
    )
    runs = list(
        session.scalars(
            select(PlatformReviewRun)
            .where(PlatformReviewRun.tenant_id == tenant_id)
            .order_by(PlatformReviewRun.id.desc()),
        ),
    )
    workers = {
        worker.id: worker
        for worker in session.scalars(select(Worker).where(Worker.tenant_id == tenant_id))
    }
    platform_observations = [
        row
        for row in session.scalars(
            select(WorkerPlatformRegistration)
            .where(WorkerPlatformRegistration.tenant_id == tenant_id)
            .order_by(WorkerPlatformRegistration.platform_name, WorkerPlatformRegistration.worker_id),
        )
        if row.source != "connector_demo"
    ]

    return {
        "generated_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "tenant_id": tenant_id,
        "company": company,
        "manifests": manifests,
        "accounts_by_manifest": _accounts_by_manifest(accounts),
        "snapshots": snapshots,
        "snapshots_by_context": _snapshots_by_context(manifests, accounts, snapshots),
        "labels_by_snapshot": _labels_by_snapshot(labels),
        "runs": runs,
        "workers": workers,
        "platform_observations": platform_observations,
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


def render_html(payload: dict[str, Any]) -> str:
    style = """
      @page { size: A4 landscape; margin: 10mm; }
      * { box-sizing: border-box; }
      body { color: #101828; font-family: Arial, sans-serif; font-size: 9.4px; }
      h1 { font-size: 20px; margin: 0 0 4px; }
      h2 { font-size: 15px; margin: 15px 0 7px; page-break-after: avoid; }
      h3 { font-size: 12px; margin: 11px 0 5px; page-break-after: avoid; }
      p { margin: 3px 0; }
      table { border-collapse: collapse; margin: 6px 0 12px; width: 100%; }
      th, td { border: 1px solid #d0d7e2; padding: 4px; vertical-align: top; }
      th { background: #eef3f8; font-weight: 700; text-align: left; }
      tr { page-break-inside: avoid; }
      .box { border: 1px solid #d0d7e2; border-radius: 4px; margin: 7px 0; padding: 7px; }
      .muted, .small { color: #52627a; }
      .small { font-size: 8.4px; }
      .page-break { page-break-before: always; }
      .mono { font-family: Consolas, monospace; }
      .label-cell { word-break: break-word; }
    """
    company = payload["company"]
    snapshot_count = len(payload["snapshots"])
    label_count = sum(len(rows) for rows in payload["labels_by_snapshot"].values())
    readonly_runs = [run for run in payload["runs"] if readonly_capture(run)]
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <title>ARM informacion obtenida de plataformas</title>
  <style>{style}</style>
</head>
<body>
  <h1>ARM - informacion obtenida de plataformas</h1>
  <p class="muted">Generado: {esc(payload["generated_at"])} | Empresa: {esc(company.name if company else "ARM")}</p>
  <div class="box">
    Este informe contiene informacion observada o registrada desde plataformas:
    contextos externos, capturas redaccionadas, etiquetas visibles, cabeceras, formularios,
    estados agregados y observaciones de trabajador/documento.
  </div>
  <div class="box">
    Plataformas ARM: {len(payload["manifests"])} |
    Capturas redaccionadas: {snapshot_count} |
    Etiquetas visibles registradas: {label_count} |
    Lecturas con captura redaccionada: {len(readonly_runs)} |
    Observaciones trabajador/plataforma: {len(payload["platform_observations"])}
  </div>
  {render_platform_contexts(payload)}
  <h2 class="page-break">Capturas redaccionadas por plataforma</h2>
  {render_snapshots(payload)}
  <h2 class="page-break">Etiquetas y campos visibles obtenidos</h2>
  {render_labels(payload)}
  <h2 class="page-break">Lecturas guiadas con informacion obtenida</h2>
  {render_readonly_runs(payload)}
  <h2 class="page-break">Observaciones registradas por trabajador/plataforma</h2>
  {render_platform_observations(payload)}
</body>
</html>"""


def render_platform_contexts(payload: dict[str, Any]) -> str:
    rows: list[str] = []
    for manifest in payload["manifests"]:
        accounts = payload["accounts_by_manifest"].get(manifest.id) or [None]
        for account in accounts:
            rows.append(
                f"""
                <tr>
                  <td><strong>{esc(manifest.platform_name)}</strong><br><span class="small">{esc(manifest.platform_slug)}</span></td>
                  <td>{esc(account.external_company_name if account else "")}</td>
                  <td>{esc(account.host if account else ", ".join(manifest.hosts or []))}</td>
                  <td>{esc(account.entry_url if account else ", ".join(manifest.entry_urls or []))}</td>
                </tr>
                """,
            )
    return f"""
      <h2>Contextos externos identificados</h2>
      <table>
        <thead><tr><th>Plataforma</th><th>Empresa/contexto externo</th><th>Host observado/configurado</th><th>URL de entrada registrada</th></tr></thead>
        <tbody>{"".join(rows) or empty_row(4)}</tbody>
      </table>
    """


def render_snapshots(payload: dict[str, Any]) -> str:
    sections: list[str] = []
    for manifest in payload["manifests"]:
        accounts = payload["accounts_by_manifest"].get(manifest.id) or [None]
        for account in accounts:
            snapshots = payload["snapshots_by_context"].get((manifest.id, account.id if account else None), [])
            rows = [
                f"""
                <tr>
                  <td>#{snapshot.id}</td>
                  <td>{esc(snapshot.platform_label)}</td>
                  <td>{esc(snapshot.host or "")}</td>
                  <td>{esc(snapshot.login_status or "")}</td>
                  <td>{esc(snapshot.source_ref or "")}</td>
                  <td>{format_summary(snapshot.summary_json)}</td>
                </tr>
                """
                for snapshot in snapshots
            ]
            sections.append(
                f"""
                <h3>{esc(manifest.platform_name)} / {esc(account.external_company_name if account else "")}</h3>
                <table>
                  <thead><tr><th>ID</th><th>Etiqueta plataforma</th><th>Host</th><th>Estado observado</th><th>Fuente</th><th>Resumen observado</th></tr></thead>
                  <tbody>{"".join(rows) or empty_row(6)}</tbody>
                </table>
                """,
            )
    return "".join(sections)


def render_labels(payload: dict[str, Any]) -> str:
    rows: list[str] = []
    for snapshot in payload["snapshots"]:
        for label in payload["labels_by_snapshot"].get(snapshot.id, []):
            rows.append(
                f"""
                <tr>
                  <td>{esc(snapshot.platform_label)}<br><span class="small">Snapshot #{snapshot.id} | {esc(snapshot.host or "")}</span></td>
                  <td>{esc(label.page_label or "")}</td>
                  <td>{esc(label.label_kind)}</td>
                  <td class="label-cell">{esc(label.raw_label)}</td>
                </tr>
                """,
            )
    return f"""
      <table>
        <thead><tr><th>Plataforma/captura</th><th>Pagina/seccion</th><th>Tipo visible</th><th>Texto/campo visible</th></tr></thead>
        <tbody>{"".join(rows) or empty_row(4)}</tbody>
      </table>
    """


def render_readonly_runs(payload: dict[str, Any]) -> str:
    sections: list[str] = []
    for run in payload["runs"]:
        capture = readonly_capture(run)
        if not capture:
            continue
        gateway = (run.evidence_json or {}).get("gateway") or {}
        pages = capture.get("pages") if isinstance(capture.get("pages"), list) else []
        page_rows = []
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_rows.append(
                f"""
                <tr>
                  <td>{esc(page.get("label") or "")}</td>
                  <td>{esc(page.get("title") or "")}<br><span class="small mono">{esc(page.get("url") or "")}</span></td>
                  <td>{list_items(page.get("headings"))}</td>
                  <td>{list_items(page.get("forms"))}</td>
                  <td>{list_items(page.get("table_headers") or page.get("grid_headers"))}</td>
                  <td>{format_status_counts(page.get("status_counts"))}</td>
                  <td>{format_target_signals(page.get("target_signals"))}</td>
                </tr>
                """,
            )
        sections.append(
            f"""
            <h3>Run #{run.id} - {esc(run.platform_name)} / {esc(gateway.get("external_company_name") or "")}</h3>
            <p class="small">Resultado registrado: {esc(run.result_status or "")} | {esc(run.result_summary or "")}</p>
            <table>
              <thead><tr><th>Paso</th><th>Pagina</th><th>Cabeceras visibles</th><th>Formularios visibles</th><th>Cabeceras de tabla</th><th>Estados agregados</th><th>Senales objetivo</th></tr></thead>
              <tbody>{"".join(page_rows) or empty_row(7)}</tbody>
            </table>
            """,
        )
    return "".join(sections) or "<p>Sin lecturas con captura redaccionada.</p>"


def render_platform_observations(payload: dict[str, Any]) -> str:
    rows: list[str] = []
    for observation in payload["platform_observations"]:
        worker = payload["workers"].get(observation.worker_id)
        rows.append(
            f"""
            <tr>
              <td>{esc(observation.platform_name)}</td>
              <td>{esc(observation.assignment_scope or "")}</td>
              <td>{esc(worker.first_name + " " + worker.last_name if worker else f"worker #{observation.worker_id}")}</td>
              <td>{esc(observation.registration_status)}</td>
              <td>{esc(observation.notes or "")}</td>
              <td>{esc(observation.last_synced_at.isoformat() if observation.last_synced_at else "")}</td>
            </tr>
            """,
        )
    return f"""
      <table>
        <thead><tr><th>Plataforma</th><th>Contexto</th><th>Trabajador</th><th>Estado observado</th><th>Observacion</th><th>Fecha registro</th></tr></thead>
        <tbody>{"".join(rows) or empty_row(6)}</tbody>
      </table>
    """


def readonly_capture(run: PlatformReviewRun) -> dict[str, Any] | None:
    gateway = (run.evidence_json or {}).get("gateway")
    if not isinstance(gateway, dict):
        return None
    capture = gateway.get("readonly_capture")
    return capture if isinstance(capture, dict) else None


def format_summary(summary: dict[str, Any]) -> str:
    if not isinstance(summary, dict):
        return ""
    visible = {
        key: value
        for key, value in summary.items()
        if key in {"pages_captured", "captcha_detected", "mfa_detected", "platform_key", "row"}
    }
    return "<br>".join(f"{esc(key)}: {esc(value)}" for key, value in visible.items())


def list_items(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return ""
    return "<br>".join(f"- {esc(item)}" for item in value[:12])


def format_status_counts(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return ""
    return "<br>".join(esc(item) for item in value)


def format_target_signals(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return ""
    return "<br>".join(f"{esc(key)}: {esc(val)}" for key, val in value.items())


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
