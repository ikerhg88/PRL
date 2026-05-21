"use client";

import {
  AlertTriangle,
  Bell,
  CheckCircle2,
  ExternalLink,
  FileText,
  RefreshCw,
  ShieldAlert,
  type LucideIcon
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { apiJson, jsonHeaders } from "../../lib/apiClient";

type StatusColor = "green" | "orange" | "red";
type SeverityFilter = "all" | StatusColor;

type PlatformReviewSchedule = {
  id: number;
  manifest_id: number;
  platform_slug: string;
  platform_name: string;
  enabled: boolean;
  last_result_status: string | null;
  last_result_summary: string | null;
  next_run_at: string | null;
};

type PlatformDataCoveragePendingItem = {
  id: string;
  kind: string;
  severity: StatusColor;
  title: string;
  detail: string;
  suggested_action: string;
};

type PlatformDataCoverageContext = {
  manifest_id: number;
  platform_slug: string;
  platform_name: string;
  account_proposal_id: number | null;
  external_company_name: string | null;
  trace_label: string;
  pending_items: PlatformDataCoveragePendingItem[];
  pending_summary: {
    total: number;
    red: number;
    orange: number;
  };
  next_action: string;
};

type PlatformDataCoverage = {
  contexts: PlatformDataCoverageContext[];
};

type AuthorizationIncident = {
  incident_key: string;
  severity: StatusColor;
  platform_name: string | null;
  entity_type: string;
  entity_id: number;
  title: string;
  detail: string;
  suggested_action: string;
  local_update_path: string;
};

type AuthorizationDashboard = {
  incidents: AuthorizationIncident[];
};

type ValidationSurfacePlatform = {
  platform_slug: string;
  readback_plan: Array<{ use: string; label: string; evidence_count: number }>;
};

type ValidationSurfaceMap = {
  platforms: ValidationSurfacePlatform[];
};

type PlatformReviewRun = {
  id: number;
  platform_name: string;
  status: string;
  result_status: string | null;
  result_summary: string | null;
};

type Worker = {
  id: number;
  first_name: string;
  last_name: string;
};

type Company = {
  id: number;
  name: string;
};

type DocumentType = {
  id: number;
  name: string;
};

type DocumentIntake = {
  id: number;
  original_filename: string;
  status: string;
  predicted_document_type_id: number | null;
  predicted_entity_type: string | null;
  predicted_worker_id: number | null;
  predicted_company_id: number | null;
  created_document_id: number | null;
  confidence: number;
};

type NotificationRow = {
  key: string;
  platform_slug: string;
  platform_name: string;
  context: string;
  severity: StatusColor;
  title: string;
  detail: string;
  action: string;
  source: string;
  localPath?: string;
  scheduleId?: number;
  accountProposalId?: number | null;
};

type EvidenceNotificationRow = {
  intake: DocumentIntake;
  typeName: string;
  owner: string;
};

export default function NotificationsPage() {
  const [schedules, setSchedules] = useState<PlatformReviewSchedule[]>([]);
  const [coverage, setCoverage] = useState<PlatformDataCoverage | null>(null);
  const [dashboard, setDashboard] = useState<AuthorizationDashboard | null>(null);
  const [surfaces, setSurfaces] = useState<ValidationSurfaceMap | null>(null);
  const [intakes, setIntakes] = useState<DocumentIntake[]>([]);
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [documentTypes, setDocumentTypes] = useState<DocumentType[]>([]);
  const [platformFilter, setPlatformFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("all");
  const [message, setMessage] = useState("Cargando notificaciones.");
  const [busy, setBusy] = useState(false);
  const [runningScheduleId, setRunningScheduleId] = useState<number | null>(null);

  useEffect(() => {
    void loadData();
  }, []);

  async function loadData() {
    setBusy(true);
    try {
      const scheduleRows = await apiJson<PlatformReviewSchedule[]>("/api/v1/platform-review-schedules/ensure?priority_group=all", {
        method: "POST"
      });
      const [coverageRows, dashboardRows, surfaceRows, intakeRows, workerRows, companyRows, typeRows] = await Promise.all([
        apiJson<PlatformDataCoverage>("/api/v1/platform-maps/data-coverage?priority_group=all"),
        apiJson<AuthorizationDashboard>("/api/v1/platform-authorizations/dashboard?priority_group=all"),
        apiJson<ValidationSurfaceMap>("/api/v1/platform-maps/validation-surfaces"),
        apiJson<DocumentIntake[]>("/api/v1/document-intake"),
        apiJson<Worker[]>("/api/v1/workers"),
        apiJson<Company[]>("/api/v1/companies"),
        apiJson<DocumentType[]>("/api/v1/document-types")
      ]);
      setSchedules(scheduleRows);
      setCoverage(coverageRows);
      setDashboard(dashboardRows);
      setSurfaces(surfaceRows);
      setIntakes(intakeRows);
      setWorkers(workerRows);
      setCompanies(companyRows);
      setDocumentTypes(typeRows);
      setMessage(`Notificaciones actualizadas: ${scheduleRows.filter((item) => item.enabled).length} plataformas activas y ${intakeRows.length} evidencias pendientes.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudieron cargar notificaciones.");
    } finally {
      setBusy(false);
    }
  }

  const rows = useMemo(
    () => buildNotificationRows({ schedules, coverage, dashboard, surfaces }),
    [coverage, dashboard, schedules, surfaces]
  );
  const evidenceRows = useMemo(
    () => buildEvidenceNotificationRows({ intakes, workers, companies, documentTypes }),
    [companies, documentTypes, intakes, workers]
  );

  const filteredRows = useMemo(
    () =>
      rows.filter((row) => {
        if (platformFilter !== "all" && row.platform_slug !== platformFilter) {
          return false;
        }
        if (severityFilter !== "all" && row.severity !== severityFilter) {
          return false;
        }
        return true;
      }),
    [platformFilter, rows, severityFilter]
  );

  const platformOptions = Array.from(new Set(rows.map((row) => row.platform_slug))).sort();
  const critical = filteredRows.filter((row) => row.severity === "red").length;
  const warnings = filteredRows.filter((row) => row.severity === "orange").length;
  const green = filteredRows.filter((row) => row.severity === "green").length;

  async function runNow(row: NotificationRow) {
    if (!row.scheduleId) {
      setMessage("Esta notificacion no tiene controlador asociado.");
      return;
    }
    setRunningScheduleId(row.scheduleId);
    try {
      const run = await apiJson<PlatformReviewRun>(`/api/v1/platform-review-schedules/${row.scheduleId}/run-now`, {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({ account_proposal_id: row.accountProposalId ?? null })
      });
      setMessage(`${run.platform_name}: ${run.result_summary ?? run.result_status ?? run.status}`);
      await loadData();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo lanzar la revision.");
    } finally {
      setRunningScheduleId(null);
    }
  }

  return (
    <main className="workspace full">
      <header className="topbar">
        <div>
          <p className="eyebrow">Operacion</p>
          <h2>Notificaciones</h2>
        </div>
        <button className="iconButton" type="button" aria-label="Actualizar notificaciones" onClick={() => void loadData()} disabled={busy}>
          <RefreshCw aria-hidden="true" size={18} />
        </button>
      </header>

      <div className={`messageBar ${isErrorMessage(message) ? "error" : "ok"}`}>
        <span>{message}</span>
      </div>

      <section className="metricGrid" aria-label="Resumen de notificaciones">
        <Metric icon={ShieldAlert} label="Criticas" value={String(critical)} />
        <Metric icon={AlertTriangle} label="Warnings" value={String(warnings)} />
        <Metric icon={FileText} label="Evidencias" value={String(evidenceRows.length)} />
        <Metric icon={Bell} label="Avisos visibles" value={String(filteredRows.length + evidenceRows.length)} />
      </section>

      <section className="panel">
        <div className="sectionTitle">
          <div>
            <p className="eyebrow">Filtros</p>
            <h3>Solo plataformas activas</h3>
          </div>
          <Bell aria-hidden="true" size={20} />
        </div>
        <div className="formGrid">
          <label>
            <span>Plataforma</span>
            <select value={platformFilter} onChange={(event) => setPlatformFilter(event.target.value)}>
              <option value="all">Todas</option>
              {platformOptions.map((slug) => (
                <option value={slug} key={slug}>{platformName(rows, slug)}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Severidad</span>
            <select value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value as SeverityFilter)}>
              <option value="all">Todas</option>
              <option value="red">Criticas</option>
              <option value="orange">Warnings</option>
              <option value="green">Informativas</option>
            </select>
          </label>
        </div>
      </section>

      <section className="panel">
        <div className="sectionTitle">
          <div>
            <p className="eyebrow">Validacion documental</p>
            <h3>Evidencias pendientes de validacion</h3>
          </div>
          <FileText aria-hidden="true" size={20} />
        </div>
        <div className="table" role="table" aria-label="Evidencias pendientes de validacion">
          <div className="tableRow evidenceHead" role="row">
            <span role="columnheader">Fichero</span>
            <span role="columnheader">Entidad</span>
            <span role="columnheader">Tipo</span>
            <span role="columnheader">Estado</span>
            <span role="columnheader">Confianza</span>
          </div>
          {evidenceRows.map(({ intake, owner, typeName }) => (
            <div className="tableRow evidenceRow" role="row" key={intake.id}>
              <span role="cell">
                <strong>{intake.original_filename}</strong>
                <small>{intake.created_document_id ? `Documento #${intake.created_document_id}` : "Sin documento preparado"}</small>
              </span>
              <span role="cell">{owner}</span>
              <span role="cell">{typeName}</span>
              <span role="cell"><span className={`statusBadge ${intake.status}`}>{intake.status}</span></span>
              <span role="cell">{formatConfidence(intake.confidence)}</span>
            </div>
          ))}
          {evidenceRows.length === 0 ? (
            <div className="tableRow evidenceRow" role="row">
              <span role="cell">Sin evidencias pendientes de validacion.</span>
              <span role="cell">ARM</span>
              <span role="cell">Documentacion</span>
              <span role="cell"><span className="statusBadge green">ok</span></span>
              <span role="cell">100%</span>
            </div>
          ) : null}
        </div>
      </section>

      <section className="panel">
        <div className="table" role="table" aria-label="Notificaciones activas">
          <div className="tableRow notificationHead" role="row">
            <span role="columnheader">Plataforma</span>
            <span role="columnheader">Severidad</span>
            <span role="columnheader">Aviso</span>
            <span role="columnheader">Accion</span>
            <span role="columnheader">Origen</span>
          </div>
          {filteredRows.map((row) => (
            <div className="tableRow notificationRow" role="row" key={row.key}>
              <span role="cell">
                <strong>{row.platform_name}</strong>
                <small>{row.context}</small>
              </span>
              <span role="cell">{renderStatus(row.severity, severityLabel(row.severity))}</span>
              <span role="cell">
                <strong>{row.title}</strong>
                <small>{row.detail}</small>
              </span>
              <span role="cell">
                {row.action}
                <small className="actionControls">
                  {row.scheduleId ? (
                    <button className="secondaryButton" type="button" onClick={() => void runNow(row)} disabled={runningScheduleId === row.scheduleId}>
                      Revisar ahora
                    </button>
                  ) : null}
                  {row.localPath ? (
                    <a className="inlineLink" href={row.localPath}>
                      Abrir
                      <ExternalLink aria-hidden="true" size={13} />
                    </a>
                  ) : null}
                </small>
              </span>
              <span role="cell">
                {row.source}
                <small>{row.platform_slug}</small>
              </span>
            </div>
          ))}
          {filteredRows.length === 0 ? (
            <div className="tableRow notificationRow" role="row">
              <span role="cell">Sin avisos para plataformas activas.</span>
              <span role="cell">{renderStatus("green", "ok")}</span>
              <span role="cell">Todo filtrado o sin pendientes.</span>
              <span role="cell">Revisa filtros o activa plataformas.</span>
              <span role="cell">Hub</span>
            </div>
          ) : null}
        </div>
      </section>
    </main>
  );
}

function buildNotificationRows({
  schedules,
  coverage,
  dashboard,
  surfaces
}: {
  schedules: PlatformReviewSchedule[];
  coverage: PlatformDataCoverage | null;
  dashboard: AuthorizationDashboard | null;
  surfaces: ValidationSurfaceMap | null;
}): NotificationRow[] {
  const activeSchedules = schedules.filter((schedule) => schedule.enabled);
  const scheduleBySlug = new Map(activeSchedules.map((schedule) => [schedule.platform_slug, schedule]));
  const surfaceBySlug = new Map((surfaces?.platforms ?? []).map((platform) => [platform.platform_slug, platform]));
  const rows: NotificationRow[] = [];

  for (const context of coverage?.contexts ?? []) {
    const schedule = scheduleBySlug.get(context.platform_slug);
    if (!schedule) {
      continue;
    }
    for (const item of context.pending_items) {
      rows.push({
        key: `coverage:${context.platform_slug}:${context.account_proposal_id}:${item.id}`,
        platform_slug: context.platform_slug,
        platform_name: context.platform_name,
        context: context.trace_label,
        severity: item.severity,
        title: item.title,
        detail: item.detail,
        action: item.suggested_action,
        source: "Mapa de plataforma",
        scheduleId: schedule.id,
        accountProposalId: context.account_proposal_id
      });
    }
  }

  for (const schedule of activeSchedules) {
    const surface = surfaceBySlug.get(schedule.platform_slug);
    if (!surface || surface.readback_plan.length === 0) {
      rows.push({
        key: `surface:${schedule.platform_slug}`,
        platform_slug: schedule.platform_slug,
        platform_name: schedule.platform_name,
        context: "Mapa de lectura posterior",
        severity: "orange",
        title: "Falta visor profundo de pendientes",
        detail: "No hay suficientes superficies mapeadas para confirmar validador, notificaciones o rechazos.",
        action: "Lanzar captura read-only profunda desde pasarela.",
        source: "Validacion posterior",
        scheduleId: schedule.id
      });
    }
    if (schedule.last_result_status && !["completed", "login_likely_success", "readonly_status_counts_available"].includes(schedule.last_result_status)) {
      rows.push({
        key: `schedule:${schedule.id}`,
        platform_slug: schedule.platform_slug,
        platform_name: schedule.platform_name,
        context: "Ultima revision",
        severity: schedule.last_result_status.includes("missing") || schedule.last_result_status.includes("failed") ? "red" : "orange",
        title: "Revision no confirmada",
        detail: schedule.last_result_summary ?? schedule.last_result_status,
        action: "Revisar ahora o abrir pasarela humana.",
        source: "Controlador 12h",
        scheduleId: schedule.id
      });
    }
  }

  for (const incident of dashboard?.incidents ?? []) {
    const schedule = activeSchedules.find((item) => item.platform_name === incident.platform_name);
    if (!schedule) {
      continue;
    }
    rows.push({
      key: `incident:${incident.incident_key}`,
      platform_slug: schedule.platform_slug,
      platform_name: schedule.platform_name,
      context: incident.entity_type,
      severity: incident.severity,
      title: incident.title,
      detail: incident.detail,
      action: incident.suggested_action,
      source: "Incidencia Hub",
      localPath: incident.local_update_path,
      scheduleId: schedule.id
    });
  }

  if (rows.length === 0) {
    for (const schedule of activeSchedules) {
      rows.push({
        key: `ok:${schedule.id}`,
        platform_slug: schedule.platform_slug,
        platform_name: schedule.platform_name,
        context: "Activa",
        severity: "green",
        title: "Sin avisos activos",
        detail: schedule.next_run_at ? `Proxima revision ${new Date(schedule.next_run_at).toLocaleString("es-ES")}` : "Sin siguiente revision programada.",
        action: "Mantener seguimiento.",
        source: "Controlador 12h",
        scheduleId: schedule.id
      });
    }
  }

  return rows.sort((left, right) => severityRank(right.severity) - severityRank(left.severity) || left.platform_name.localeCompare(right.platform_name));
}

function buildEvidenceNotificationRows({
  intakes,
  workers,
  companies,
  documentTypes
}: {
  intakes: DocumentIntake[];
  workers: Worker[];
  companies: Company[];
  documentTypes: DocumentType[];
}): EvidenceNotificationRow[] {
  const workerById = new Map(workers.map((worker) => [worker.id, worker]));
  const companyById = new Map(companies.map((company) => [company.id, company]));
  const documentTypeById = new Map(documentTypes.map((type) => [type.id, type]));
  return intakes.map((intake) => {
    const worker = intake.predicted_worker_id ? workerById.get(intake.predicted_worker_id) : null;
    const company = intake.predicted_company_id ? companyById.get(intake.predicted_company_id) : null;
    const owner = worker
      ? workerName(worker)
      : company?.name ?? (intake.predicted_entity_type === "company" ? "Empresa ARM" : "Pendiente revisar");
    const typeName = intake.predicted_document_type_id
      ? documentTypeById.get(intake.predicted_document_type_id)?.name ?? "Tipo pendiente"
      : "Tipo pendiente";
    return { intake, owner, typeName };
  });
}

function Metric({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return (
    <article className="metric">
      <Icon aria-hidden="true" size={20} />
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function workerName(worker: Worker) {
  return `${worker.first_name} ${worker.last_name}`.trim();
}

function formatConfidence(confidence: number) {
  const percent = confidence <= 1 ? confidence * 100 : confidence;
  return `${Math.round(percent)}%`;
}

function renderStatus(status: StatusColor, label: string) {
  const Icon = status === "green" ? CheckCircle2 : AlertTriangle;
  return (
    <span className={`statusBadge ${status}`}>
      <Icon aria-hidden="true" size={13} />
      {label}
    </span>
  );
}

function severityLabel(status: StatusColor) {
  return status === "red" ? "critica" : status === "orange" ? "warning" : "info";
}

function severityRank(status: StatusColor) {
  return status === "red" ? 2 : status === "orange" ? 1 : 0;
}

function platformName(rows: NotificationRow[], slug: string) {
  return rows.find((row) => row.platform_slug === slug)?.platform_name ?? slug;
}

function isErrorMessage(message: string) {
  return message.startsWith("HTTP") || message.startsWith("No se") || message.startsWith("Invalid") || message.includes("error") || message.includes("token");
}
