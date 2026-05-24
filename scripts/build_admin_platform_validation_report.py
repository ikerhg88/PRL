from __future__ import annotations

# ruff: noqa: E402

import argparse
import html
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

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
    Document,
    DocumentIntake,
    PlatformReviewRun,
    PlatformRpaAccountProposal,
    PlatformRpaManifest,
    Worker,
    WorkerPlatformRegistration,
)
from app.db.session import get_session_factory
from app.services.platform_data_coverage import build_platform_data_coverage


STATUS_LABELS = {
    "missing_required_document": "Falta documento requerido",
    "not_synced": "No sincronizado",
    "active": "Activo",
    "pending": "Pendiente",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an administrative PDF for ARM platform employee validation.")
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--company-id", type=int, default=None)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "artifacts" / "admin-validation")
    parser.add_argument("--no-pdf", action="store_true", help="Only write HTML, do not render PDF.")
    args = parser.parse_args()

    create_demo_database()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = args.out_dir / f"arm_platform_employee_validation_{now}"

    with get_session_factory()() as session:
        report = build_report_payload(session, tenant_id=args.tenant_id, company_id=args.company_id)

    html_body = render_html(report)
    html_path = base.with_suffix(".html")
    html_path.write_text(html_body, encoding="utf-8")
    pdf_path = base.with_suffix(".pdf")
    if not args.no_pdf:
        render_pdf(html_path, pdf_path)
    print(f"HTML: {html_path}")
    if pdf_path.exists():
        print(f"PDF: {pdf_path}")


def build_report_payload(session: Any, *, tenant_id: int, company_id: int | None) -> dict[str, Any]:
    company = session.scalars(
        select(Company)
        .where(Company.tenant_id == tenant_id)
        .where(Company.id == company_id if company_id is not None else Company.id.is_not(None))
        .order_by(Company.id)
    ).first()
    if company is None:
        raise RuntimeError("No company found for report.")

    workers = list(
        session.scalars(
            select(Worker)
            .where(Worker.tenant_id == tenant_id, Worker.company_id == company.id)
            .order_by(Worker.last_name, Worker.first_name)
        )
    )
    registrations = list(
        session.scalars(
            select(WorkerPlatformRegistration).where(
                WorkerPlatformRegistration.tenant_id == tenant_id,
                WorkerPlatformRegistration.worker_id.in_([worker.id for worker in workers] or [-1]),
            )
        )
    )
    registrations_by_worker: dict[int, list[WorkerPlatformRegistration]] = {}
    for registration in registrations:
        registrations_by_worker.setdefault(registration.worker_id, []).append(registration)

    document_counts = {
        worker_id: count
        for worker_id, count in session.execute(
            select(Document.entity_id, func.count(Document.id)).where(
                Document.tenant_id == tenant_id,
                Document.entity_type == "worker",
                Document.entity_id.in_([worker.id for worker in workers] or [-1]),
            ).group_by(Document.entity_id)
        )
    }
    intake_counts = {
        "pending_total": session.scalar(
            select(func.count(DocumentIntake.id)).where(
                DocumentIntake.tenant_id == tenant_id,
                DocumentIntake.status == "pending_review",
            )
        )
        or 0,
        "pending_worker": session.scalar(
            select(func.count(DocumentIntake.id)).where(
                DocumentIntake.tenant_id == tenant_id,
                DocumentIntake.status == "pending_review",
                DocumentIntake.predicted_entity_type == "worker",
            )
        )
        or 0,
        "pending_company": session.scalar(
            select(func.count(DocumentIntake.id)).where(
                DocumentIntake.tenant_id == tenant_id,
                DocumentIntake.status == "pending_review",
                DocumentIntake.predicted_entity_type == "company",
            )
        )
        or 0,
    }
    manifests = list(
        session.scalars(
            select(PlatformRpaManifest)
            .where(PlatformRpaManifest.tenant_id == tenant_id)
            .order_by(PlatformRpaManifest.platform_name)
        )
    )
    accounts_by_manifest: dict[int, list[PlatformRpaAccountProposal]] = {}
    for account in session.scalars(
        select(PlatformRpaAccountProposal)
        .where(PlatformRpaAccountProposal.tenant_id == tenant_id)
        .order_by(PlatformRpaAccountProposal.external_company_name)
    ):
        accounts_by_manifest.setdefault(account.manifest_id, []).append(account)
    latest_runs = list(
        session.scalars(
            select(PlatformReviewRun)
            .where(PlatformReviewRun.tenant_id == tenant_id)
            .order_by(PlatformReviewRun.id.desc())
            .limit(10)
        )
    )
    coverage = build_platform_data_coverage(session, tenant_id=tenant_id, company_id=company.id, priority_group="all")
    return {
        "generated_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "company": company,
        "workers": workers,
        "registrations_by_worker": registrations_by_worker,
        "document_counts": document_counts,
        "intake_counts": intake_counts,
        "manifests": manifests,
        "accounts_by_manifest": accounts_by_manifest,
        "latest_runs": latest_runs,
        "coverage": coverage,
    }


def render_html(report: dict[str, Any]) -> str:
    company = report["company"]
    worker_rows = "\n".join(render_worker_row(worker, report) for worker in report["workers"])
    platform_sections = "\n".join(render_platform_section(manifest, report) for manifest in report["manifests"])
    run_rows = "\n".join(render_run_row(run) for run in report["latest_runs"]) or empty_row(5)
    coverage_totals = report["coverage"]["totals"]
    style = """
      @page { size: A4 landscape; margin: 12mm; }
      * { box-sizing: border-box; }
      body { font-family: Arial, sans-serif; color: #101828; font-size: 11px; }
      h1 { font-size: 22px; margin: 0 0 4px; }
      h2 { font-size: 16px; margin: 18px 0 8px; page-break-after: avoid; }
      h3 { font-size: 13px; margin: 12px 0 6px; page-break-after: avoid; }
      p { margin: 4px 0; }
      .muted { color: #52627a; }
      .box { border: 1px solid #d0d7e2; padding: 8px; border-radius: 4px; margin: 8px 0; }
      .warn { border-color: #f4bf7a; background: #fff8ed; }
      .ok { border-color: #9ad7b1; background: #f1fff5; }
      table { width: 100%; border-collapse: collapse; margin: 8px 0 14px; page-break-inside: auto; }
      tr { page-break-inside: avoid; page-break-after: auto; }
      th, td { border: 1px solid #d0d7e2; padding: 5px; vertical-align: top; }
      th { background: #eef3f8; text-align: left; font-weight: 700; }
      .small { font-size: 10px; color: #52627a; }
      .badge { display: inline-block; border-radius: 10px; padding: 2px 6px; margin: 1px; background: #eef3f8; }
      .red { background: #fde8e8; color: #9b1c1c; }
      .orange { background: #fff2cc; color: #8a4b00; }
      .green { background: #dff6e7; color: #0b6b33; }
      .page-break { page-break-before: always; }
      .validation td:last-child, .validation th:last-child { width: 26%; }
    """
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <title>Validacion administrativa ARM plataformas</title>
  <style>{style}</style>
</head>
<body>
  <h1>Validacion administrativa de plataformas y trabajadores</h1>
  <p class="muted">Generado: {escape(report["generated_at"])} · Empresa: {escape(company.name)} · CIF: {escape(company.tax_id or "pendiente")}</p>
  <div class="box warn">
    <strong>Alcance y fuente.</strong>
    Este documento usa datos del Hub ARM, registros de plataforma, evidencias redaccionadas y mapeos contractuales.
    No incluye contrasenas, cookies, tokens, HTML completo ni valores de filas externas no aprobadas.
    Donde no hay lectura externa confirmada, se marca como pendiente de validacion.
  </div>
  <div class="box">
    <strong>Resumen.</strong>
    Trabajadores ARM: {len(report["workers"])} · Plataformas: {len(report["manifests"])} · Contextos plataforma/empresa: {coverage_totals["contexts"]} ·
    Categorias completas pendientes de revision: {coverage_totals["mapped"]} · Categorias parciales: {coverage_totals["partial"]} ·
    Claves obligatorias pendientes: {coverage_totals["missing_required_keys"]} · Documentos OCR pendientes: {report["intake_counts"]["pending_total"]}.
  </div>

  <h2>1. Trabajadores ARM para validar</h2>
  <table class="validation">
    <thead>
      <tr>
        <th>Trabajador</th>
        <th>Identificacion minima</th>
        <th>Puesto / centro</th>
        <th>Aptitud laboral</th>
        <th>Documentos Hub</th>
        <th>Plataformas donde consta</th>
        <th>Validacion administrativa</th>
      </tr>
    </thead>
    <tbody>{worker_rows}</tbody>
  </table>

  <h2 class="page-break">2. Plataformas y empleados detectados</h2>
  {platform_sections}

  <h2 class="page-break">3. Lecturas y evidencias recientes</h2>
  <table>
    <thead>
      <tr>
        <th>ID</th>
        <th>Plataforma</th>
        <th>Estado</th>
        <th>Resultado</th>
        <th>Resumen</th>
      </tr>
    </thead>
    <tbody>{run_rows}</tbody>
  </table>

  <h2>4. Tareas de validacion</h2>
  <table class="validation">
    <thead>
      <tr>
        <th>Prioridad</th>
        <th>Elemento</th>
        <th>Comprobacion</th>
        <th>Validacion administrativa</th>
      </tr>
    </thead>
    <tbody>
      <tr><td>Alta</td><td>CTAIMA/SOFIDEL</td><td>Confirmar si falta Entrega de EPIs para Eleder Bilbao y si debe subirse/regularizarse.</td><td>OK / Corregir / Notas:</td></tr>
      <tr><td>Alta</td><td>Trabajadores sin plataforma</td><td>Confirmar si los 6 trabajadores sin registro deben estar dados de alta en CTAIMA, e-coordina, Nomio, Timenet, Validate, Vitaly CAE o 6conecta.</td><td>OK / Corregir / Notas:</td></tr>
      <tr><td>Media</td><td>Datos incompletos</td><td>Completar DNI/NIE, NAF, puesto, centro y aptitud laboral cuando proceda.</td><td>OK / Corregir / Notas:</td></tr>
      <tr><td>Media</td><td>Mapeos pendientes</td><td>Aprobar equivalencias de documentos y estados antes de persistir datos externos fila a fila.</td><td>OK / Corregir / Notas:</td></tr>
    </tbody>
  </table>
</body>
</html>"""


def render_worker_row(worker: Worker, report: dict[str, Any]) -> str:
    registrations = report["registrations_by_worker"].get(worker.id, [])
    registration_text = "<br>".join(format_registration(registration) for registration in registrations) or "No consta alta externa en el Hub"
    return f"""
      <tr>
        <td><strong>{escape(worker.first_name)} {escape(worker.last_name)}</strong><br><span class="small">ID Hub #{worker.id}</span></td>
        <td>{escape(worker.identifier_type or "pendiente")} · ult.4: {escape(worker.identifier_last4 or "pendiente")}<br>NAF ult.4: {escape(worker.social_security_last4 or "pendiente")}</td>
        <td>{escape(worker.work_position or "pendiente")}<br><span class="small">{escape(worker.work_center_name or "centro pendiente")}</span></td>
        <td>{escape(worker.medical_fitness_status or "pendiente")}<br><span class="small">Cad.: {escape(format_date(worker.medical_fitness_expires_at))}</span></td>
        <td>{report["document_counts"].get(worker.id, 0)} documentos aprobados en Hub</td>
        <td>{registration_text}</td>
        <td>OK / Corregir / Notas:</td>
      </tr>
    """


def render_platform_section(manifest: PlatformRpaManifest, report: dict[str, Any]) -> str:
    accounts = report["accounts_by_manifest"].get(manifest.id, [])
    account_labels = ", ".join(escape(account.external_company_name or "sin empresa externa") for account in accounts) or "sin cuentas"
    platform_workers = [
        (worker, registration)
        for worker in report["workers"]
        for registration in report["registrations_by_worker"].get(worker.id, [])
        if registration.platform_name == manifest.platform_name
        or registration.platform_name.lower().startswith(manifest.platform_name.lower().split("/")[0].strip())
    ]
    rows = "\n".join(render_platform_worker_row(worker, registration) for worker, registration in platform_workers)
    if not rows:
        rows = """
          <tr>
            <td colspan="5">No hay empleados confirmados en esta plataforma dentro del Hub. Requiere lectura externa o validacion administrativa.</td>
          </tr>
        """
    return f"""
      <h3>{escape(manifest.platform_name)}</h3>
      <p class="small">Contextos externos: {account_labels}</p>
      <table class="validation">
        <thead>
          <tr>
            <th>Empleado</th>
            <th>Empresa/contexto externo</th>
            <th>Estado plataforma</th>
            <th>Observacion</th>
            <th>Validacion administrativa</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    """


def render_platform_worker_row(worker: Worker, registration: WorkerPlatformRegistration) -> str:
    return f"""
      <tr>
        <td>{escape(worker.first_name)} {escape(worker.last_name)}</td>
        <td>{escape(registration.assignment_scope or "pendiente")}</td>
        <td>{escape(STATUS_LABELS.get(registration.registration_status, registration.registration_status))}</td>
        <td>{escape(registration.notes or "Sin observacion")}</td>
        <td>OK / Corregir / Notas:</td>
      </tr>
    """


def render_run_row(run: PlatformReviewRun) -> str:
    return f"""
      <tr>
        <td>#{run.id}</td>
        <td>{escape(run.platform_name)}</td>
        <td>{escape(run.status)}</td>
        <td>{escape(run.result_status or "pendiente")}</td>
        <td>{escape(run.result_summary or run.error_summary or "sin resumen")}</td>
      </tr>
    """


def format_registration(registration: WorkerPlatformRegistration) -> str:
    scope = f" / {registration.assignment_scope}" if registration.assignment_scope else ""
    status = STATUS_LABELS.get(registration.registration_status, registration.registration_status)
    return f"<span class=\"badge orange\">{escape(registration.platform_name)}{escape(scope)}: {escape(status)}</span>"


def render_pdf(html_path: Path, pdf_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = None
        launch_attempts: list[dict[str, Any]] = [
            {"channel": "chrome"},
            {"channel": "msedge"},
        ]
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


def format_date(value: Any) -> str:
    return value.isoformat() if value else "pendiente"


def escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def empty_row(columns: int) -> str:
    return f"<tr><td colspan=\"{columns}\">Sin datos registrados.</td></tr>"


if __name__ == "__main__":
    main()
