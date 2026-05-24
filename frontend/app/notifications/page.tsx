"use client";

import {
  AlertTriangle,
  Ban,
  Bell,
  CheckCircle2,
  ExternalLink,
  FileText,
  RefreshCw,
  RotateCcw,
  Send,
  ShieldAlert,
  type LucideIcon
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { apiJson, jsonHeaders } from "../../lib/apiClient";

type StatusColor = "green" | "orange" | "red";
type SeverityFilter = "all" | StatusColor;
type VisibilityFilter = "visible" | "dismissed" | "all";
type SourceFilter = "all" | "observed" | "platform" | "surface" | "schedule" | "incident" | "evidence";
type EvidenceStatusFilter = "all" | "pending_review" | "accepted" | "other";
type DismissedNotification = {
  key: string;
  dismissedAt: string;
};

type PlatformReviewSchedule = {
  id: number;
  manifest_id: number;
  platform_slug: string;
  platform_name: string;
  enabled: boolean;
  last_result_status: string | null;
  last_result_summary: string | null;
  last_run_at: string | null;
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
  created_at: string | null;
  reviewed_at: string | null;
};

type PlatformObservedDocumentRequest = {
  id: number;
  manifest_id: number;
  account_proposal_id: number | null;
  external_platform_id: number | null;
  platform_account_id: number | null;
  source_run_id: number | null;
  entity_scope: string;
  local_company_id: number | null;
  local_worker_id: number | null;
  document_type_id: number | null;
  matched_document_id: number | null;
  matched_document_version_id: number | null;
  external_requirement_key: string;
  external_requirement_label: string;
  external_entity_label: string | null;
  external_status: string;
  status_color: StatusColor;
  severity: StatusColor;
  external_comment: string | null;
  rejection_reason: string | null;
  confidence: number;
  source: string;
  source_page_label: string | null;
  last_seen_at: string;
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
  sourceKind: SourceFilter;
  createdAt: string | null;
  localPath?: string;
  scheduleId?: number;
  accountProposalId?: number | null;
};

type EvidenceNotificationRow = {
  key: string;
  intake: DocumentIntake;
  typeName: string;
  owner: string;
  createdAt: string | null;
};

type MassUpdatePlan = {
  summary: {
    actions: number;
    document_requests: number;
    missing_workers: number;
    ready_for_submit: number;
    blocked: number;
    capture_recommended: number;
    with_live_helper: number;
  };
  actions: Array<{
    action_id: string;
    kind: string;
    platform_name: string;
    external_company_name: string | null;
    title: string;
    preview_status: string;
    next_action: string;
  }>;
};

type MassUpdateSubmitResult = {
  summary: {
    selected_actions: number;
    transfer_jobs_created: number;
    capture_requests_created: number;
    blocked: number;
    confirmed_external: number;
  };
};

type WriteMaturationResult = {
  summary: {
    targets: number;
    capture_requests_created: number;
    capture_requests_authorized: number;
    browsers_launched: number;
    captures_synced: number;
    write_paths_approved: number;
    write_paths_blocked: number;
    write_ready_contexts: number;
    fully_mapped_for_read_write: number;
    external_write_executed: number;
  };
};

const dismissedStorageKey = "iprl_cae_dismissed_notifications";

export default function NotificationsPage() {
  const [schedules, setSchedules] = useState<PlatformReviewSchedule[]>([]);
  const [coverage, setCoverage] = useState<PlatformDataCoverage | null>(null);
  const [dashboard, setDashboard] = useState<AuthorizationDashboard | null>(null);
  const [surfaces, setSurfaces] = useState<ValidationSurfaceMap | null>(null);
  const [observedRequests, setObservedRequests] = useState<PlatformObservedDocumentRequest[]>([]);
  const [intakes, setIntakes] = useState<DocumentIntake[]>([]);
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [documentTypes, setDocumentTypes] = useState<DocumentType[]>([]);
  const [platformFilter, setPlatformFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("all");
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");
  const [visibilityFilter, setVisibilityFilter] = useState<VisibilityFilter>("visible");
  const [evidenceStatusFilter, setEvidenceStatusFilter] = useState<EvidenceStatusFilter>("all");
  const [search, setSearch] = useState("");
  const [hideBeforeDate, setHideBeforeDate] = useState("");
  const [dismissedRows, setDismissedRows] = useState<Record<string, DismissedNotification>>({});
  const [message, setMessage] = useState("Cargando notificaciones.");
  const [busy, setBusy] = useState(false);
  const [runningScheduleId, setRunningScheduleId] = useState<number | null>(null);
  const [massPlan, setMassPlan] = useState<MassUpdatePlan | null>(null);
  const [preparingMassUpdate, setPreparingMassUpdate] = useState(false);
  const [maturingWrites, setMaturingWrites] = useState(false);

  useEffect(() => {
    setDismissedRows(readDismissedRows());
    void loadData();
  }, []);

  async function loadData() {
    setBusy(true);
    try {
      const scheduleRows = await apiJson<PlatformReviewSchedule[]>("/api/v1/platform-review-schedules/ensure?priority_group=all", {
        method: "POST"
      });
      const [coverageRows, dashboardRows, surfaceRows, observedRequestRows, intakeRows, workerRows, companyRows, typeRows, massPlanRows] = await Promise.all([
        apiJson<PlatformDataCoverage>("/api/v1/platform-maps/data-coverage?priority_group=all"),
        apiJson<AuthorizationDashboard>("/api/v1/platform-authorizations/dashboard?priority_group=all"),
        apiJson<ValidationSurfaceMap>("/api/v1/platform-maps/validation-surfaces"),
        apiJson<PlatformObservedDocumentRequest[]>("/api/v1/platform-observations/document-requests?only_actionable=true&limit=500"),
        apiJson<DocumentIntake[]>("/api/v1/document-intake"),
        apiJson<Worker[]>("/api/v1/workers"),
        apiJson<Company[]>("/api/v1/companies"),
        apiJson<DocumentType[]>("/api/v1/document-types"),
        apiJson<MassUpdatePlan>("/api/v1/exchange/mass-update/plan", {
          method: "POST",
          headers: jsonHeaders(),
          body: JSON.stringify({
            include_missing_workers: true,
            include_document_requests: true,
            only_active_contexts: true,
            limit: 200
          })
        })
      ]);
      setSchedules(scheduleRows);
      setCoverage(coverageRows);
      setDashboard(dashboardRows);
      setSurfaces(surfaceRows);
      setObservedRequests(observedRequestRows);
      setIntakes(intakeRows);
      setWorkers(workerRows);
      setCompanies(companyRows);
      setDocumentTypes(typeRows);
      setMassPlan(massPlanRows);
      setMessage(`Notificaciones actualizadas: ${scheduleRows.filter((item) => item.enabled).length} plataformas activas, ${observedRequestRows.length} peticiones externas, ${intakeRows.length} evidencias HUB y ${massPlanRows.summary.actions} acciones masivas propuestas.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudieron cargar notificaciones.");
    } finally {
      setBusy(false);
    }
  }

  const rows = useMemo(
    () => buildNotificationRows({ schedules, coverage, dashboard, surfaces, observedRequests, workers, companies, documentTypes }),
    [coverage, dashboard, documentTypes, observedRequests, schedules, surfaces, workers, companies]
  );
  const evidenceRows = useMemo(
    () => buildEvidenceNotificationRows({ intakes, workers, companies, documentTypes }),
    [companies, documentTypes, intakes, workers]
  );

  const filteredRows = useMemo(
    () =>
      rows.filter((row) => {
        const dismissed = Boolean(dismissedRows[row.key]);
        if (visibilityFilter === "visible" && dismissed) {
          return false;
        }
        if (visibilityFilter === "dismissed" && !dismissed) {
          return false;
        }
        if (platformFilter !== "all" && row.platform_slug !== platformFilter) {
          return false;
        }
        if (severityFilter !== "all" && row.severity !== severityFilter) {
          return false;
        }
        if (sourceFilter !== "all" && row.sourceKind !== sourceFilter) {
          return false;
        }
        if (isOlderThan(row.createdAt, hideBeforeDate)) {
          return false;
        }
        if (!matchesQuery(search, [row.platform_name, row.context, row.title, row.detail, row.action, row.source])) {
          return false;
        }
        return true;
      }),
    [dismissedRows, hideBeforeDate, platformFilter, rows, search, severityFilter, sourceFilter, visibilityFilter]
  );

  const filteredEvidenceRows = useMemo(
    () =>
      evidenceRows.filter((row) => {
        const dismissed = Boolean(dismissedRows[row.key]);
        if (visibilityFilter === "visible" && dismissed) {
          return false;
        }
        if (visibilityFilter === "dismissed" && !dismissed) {
          return false;
        }
        if (sourceFilter !== "all" && sourceFilter !== "evidence") {
          return false;
        }
        if (evidenceStatusFilter === "pending_review" && row.intake.status !== "pending_review") {
          return false;
        }
        if (evidenceStatusFilter === "accepted" && row.intake.status !== "accepted") {
          return false;
        }
        if (evidenceStatusFilter === "other" && ["pending_review", "accepted"].includes(row.intake.status)) {
          return false;
        }
        if (isOlderThan(row.createdAt, hideBeforeDate)) {
          return false;
        }
        if (!matchesQuery(search, [row.intake.original_filename, row.owner, row.typeName, row.intake.status])) {
          return false;
        }
        return true;
      }),
    [dismissedRows, evidenceRows, evidenceStatusFilter, hideBeforeDate, search, sourceFilter, visibilityFilter]
  );

  const platformOptions = Array.from(new Set(rows.map((row) => row.platform_slug))).sort();
  const critical = filteredRows.filter((row) => row.severity === "red").length;
  const warnings = filteredRows.filter((row) => row.severity === "orange").length;
  const dismissedCount = [...rows.map((row) => row.key), ...evidenceRows.map((row) => row.key)].filter((key) => dismissedRows[key]).length;

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

  async function prepareMassUpdate() {
    setPreparingMassUpdate(true);
    try {
      const result = await apiJson<MassUpdateSubmitResult>("/api/v1/exchange/mass-update/submit", {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({
          include_missing_workers: true,
          include_document_requests: true,
          only_active_contexts: true,
          limit: 200,
          dry_run: true,
          manual_approval_required: true,
          live_external_write_authorized: false,
          create_capture_requests: true
        })
      });
      setMessage(`Actualizacion masiva preparada: ${result.summary.transfer_jobs_created} job(s), ${result.summary.capture_requests_created} pasarela(s), ${result.summary.blocked} bloqueo(s), ${result.summary.confirmed_external} confirmadas.`);
      await loadData();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo preparar la actualizacion masiva.");
    } finally {
      setPreparingMassUpdate(false);
    }
  }

  async function matureWriteReadiness() {
    setMaturingWrites(true);
    try {
      const result = await apiJson<WriteMaturationResult>("/api/v1/exchange/write-readiness/mature", {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({
          create_missing_capture_requests: true,
          authorize_capture_requests: true,
          launch_browsers: false,
          sync_available_captures: true,
          approve_valid_captured_paths: true,
          max_browser_launches: 0
        })
      });
      setMessage(`Mapeo madurado: ${result.summary.capture_requests_authorized} pasarela(s) autorizada(s), ${result.summary.captures_synced} captura(s), ${result.summary.write_paths_approved} path(s) aprobado(s), ${result.summary.write_ready_contexts} contexto(s) listos.`);
      await loadData();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo madurar el mapeo de escritura.");
    } finally {
      setMaturingWrites(false);
    }
  }

  function dismissNotification(key: string) {
    const next = {
      ...dismissedRows,
      [key]: {
        key,
        dismissedAt: new Date().toISOString()
      }
    };
    setDismissedRows(next);
    writeDismissedRows(next);
    setMessage("Aviso anulado en esta vista del Hub. Puedes recuperarlo con el filtro de anuladas.");
  }

  function restoreNotification(key: string) {
    const next = { ...dismissedRows };
    delete next[key];
    setDismissedRows(next);
    writeDismissedRows(next);
    setMessage("Aviso restaurado.");
  }

  function clearDateFilter() {
    setHideBeforeDate("");
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
        <Metric icon={FileText} label="Evidencias" value={String(filteredEvidenceRows.length)} />
        <Metric icon={Bell} label="Avisos visibles / anulados" value={`${filteredRows.length + filteredEvidenceRows.length} / ${dismissedCount}`} />
      </section>

      <section className="panel">
        <div className="sectionTitle">
          <div>
            <p className="eyebrow">Actualizacion masiva</p>
            <h3>Preparar cambios desde el Hub</h3>
          </div>
          <Send aria-hidden="true" size={20} />
        </div>
        <div className="massUpdateGrid">
          <article>
            <span>Acciones propuestas</span>
            <strong>{massPlan?.summary.actions ?? 0}</strong>
            <small>{massPlan?.summary.document_requests ?? 0} documentos pedidos / {massPlan?.summary.missing_workers ?? 0} altas pendientes</small>
          </article>
          <article>
            <span>Preview listo</span>
            <strong>{massPlan?.summary.ready_for_submit ?? 0}</strong>
            <small>{massPlan?.summary.blocked ?? 0} bloqueadas por datos, mapeo o helper</small>
          </article>
          <article>
            <span>Pasarela recomendada</span>
            <strong>{massPlan?.summary.capture_recommended ?? 0}</strong>
            <small>{massPlan?.summary.with_live_helper ?? 0} con helper live</small>
          </article>
        </div>
        <div className="notice">
          <ShieldAlert aria-hidden="true" size={18} />
          <p>El Hub prepara jobs en dry-run y crea pasarelas de mapeo cuando falte lectura, helper o paths aprobados. No se ejecuta escritura externa sin preview, aprobacion y lectura posterior.</p>
        </div>
        <div className="actionControls">
          <button className="primaryButton inlineButton" type="button" onClick={() => void prepareMassUpdate()} disabled={busy || preparingMassUpdate || !massPlan?.summary.actions}>
            <Send aria-hidden="true" size={16} />
            Preparar actualizaciones
          </button>
          <button className="secondaryButton inlineButton" type="button" onClick={() => void loadData()} disabled={busy || preparingMassUpdate}>
            <RefreshCw aria-hidden="true" size={16} />
            Recalcular plan
          </button>
          <button className="secondaryButton inlineButton" type="button" onClick={() => void matureWriteReadiness()} disabled={busy || preparingMassUpdate || maturingWrites}>
            <CheckCircle2 aria-hidden="true" size={16} />
            Madurar mapeos
          </button>
        </div>
        {massPlan?.actions.length ? (
          <div className="massUpdatePreview" aria-label="Primeras acciones masivas">
            {massPlan.actions.slice(0, 5).map((action) => (
              <article key={action.action_id}>
                <strong>{action.platform_name} / {action.external_company_name ?? "sin empresa externa"}</strong>
                <span>{action.title}</span>
                <small>{action.preview_status}: {action.next_action}</small>
              </article>
            ))}
          </div>
        ) : null}
      </section>

      <section className="panel" aria-label="Filtros de notificaciones">
        <div className="sectionTitle">
          <div>
            <p className="eyebrow">Filtros</p>
            <h3>Solo plataformas activas</h3>
          </div>
          <Bell aria-hidden="true" size={20} />
        </div>
        <div className="formGrid">
          <label>
            <span>Buscar</span>
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Fichero, trabajador, plataforma, aviso..." />
          </label>
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
          <label>
            <span>Origen</span>
            <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value as SourceFilter)}>
              <option value="all">Todos</option>
              <option value="observed">Peticiones leidas</option>
              <option value="platform">Mapa plataforma</option>
              <option value="surface">Superficies</option>
              <option value="schedule">Revision 12h</option>
              <option value="incident">Incidencias Hub</option>
              <option value="evidence">Evidencias</option>
            </select>
          </label>
          <label>
            <span>Estado evidencia</span>
            <select value={evidenceStatusFilter} onChange={(event) => setEvidenceStatusFilter(event.target.value as EvidenceStatusFilter)}>
              <option value="all">Todos</option>
              <option value="pending_review">Pendientes</option>
              <option value="accepted">Aceptadas</option>
              <option value="other">Otros</option>
            </select>
          </label>
          <label>
            <span>Visibilidad</span>
            <select value={visibilityFilter} onChange={(event) => setVisibilityFilter(event.target.value as VisibilityFilter)}>
              <option value="visible">Visibles</option>
              <option value="dismissed">Anuladas</option>
              <option value="all">Todas</option>
            </select>
          </label>
          <label>
            <span>Ocultar anteriores a</span>
            <input type="date" value={hideBeforeDate} onChange={(event) => setHideBeforeDate(event.target.value)} />
          </label>
        </div>
        <div className="filterHint">
          <span>{hideBeforeDate ? `Ocultando avisos anteriores a ${formatDate(hideBeforeDate)}.` : "Sin corte de fecha: se muestran avisos segun filtros."}</span>
          {hideBeforeDate ? (
            <button className="secondaryButton inlineButton" type="button" onClick={clearDateFilter}>
              Quitar fecha
            </button>
          ) : null}
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
          {filteredEvidenceRows.map(({ key, intake, owner, typeName, createdAt }) => (
            <div className="tableRow evidenceRow" role="row" key={intake.id}>
              <span role="cell">
                <strong>{intake.original_filename}</strong>
                <small>{intake.created_document_id ? `Documento #${intake.created_document_id}` : "Sin documento preparado"} / {formatDateTime(createdAt)}</small>
              </span>
              <span role="cell">{owner}</span>
              <span role="cell">{typeName}</span>
              <span role="cell"><span className={`statusBadge ${intake.status}`}>{intake.status}</span></span>
              <span role="cell">
                {formatConfidence(intake.confidence)}
                <small className="actionControls">
                  {dismissedRows[key] ? (
                    <button className="secondaryButton" type="button" onClick={() => restoreNotification(key)}>
                      <RotateCcw aria-hidden="true" size={13} />
                      Restaurar
                    </button>
                  ) : (
                    <button className="secondaryButton" type="button" onClick={() => dismissNotification(key)}>
                      <Ban aria-hidden="true" size={13} />
                      Anular
                    </button>
                  )}
                </small>
              </span>
            </div>
          ))}
          {filteredEvidenceRows.length === 0 ? (
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
                  {dismissedRows[row.key] ? (
                    <button className="secondaryButton" type="button" onClick={() => restoreNotification(row.key)}>
                      <RotateCcw aria-hidden="true" size={13} />
                      Restaurar
                    </button>
                  ) : (
                    <button className="secondaryButton" type="button" onClick={() => dismissNotification(row.key)}>
                      <Ban aria-hidden="true" size={13} />
                      Anular
                    </button>
                  )}
                </small>
              </span>
              <span role="cell">
                {row.source}
                <small>{row.platform_slug} / {formatDateTime(row.createdAt)}</small>
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
  surfaces,
  observedRequests,
  workers,
  companies,
  documentTypes
}: {
  schedules: PlatformReviewSchedule[];
  coverage: PlatformDataCoverage | null;
  dashboard: AuthorizationDashboard | null;
  surfaces: ValidationSurfaceMap | null;
  observedRequests: PlatformObservedDocumentRequest[];
  workers: Worker[];
  companies: Company[];
  documentTypes: DocumentType[];
}): NotificationRow[] {
  const activeSchedules = schedules.filter((schedule) => schedule.enabled);
  const scheduleBySlug = new Map(activeSchedules.map((schedule) => [schedule.platform_slug, schedule]));
  const scheduleByManifest = new Map(activeSchedules.map((schedule) => [schedule.manifest_id, schedule]));
  const surfaceBySlug = new Map((surfaces?.platforms ?? []).map((platform) => [platform.platform_slug, platform]));
  const contextByAccount = new Map(
    (coverage?.contexts ?? [])
      .filter((context) => context.account_proposal_id !== null)
      .map((context) => [context.account_proposal_id as number, context])
  );
  const workerById = new Map(workers.map((worker) => [worker.id, worker]));
  const companyById = new Map(companies.map((company) => [company.id, company]));
  const typeById = new Map(documentTypes.map((type) => [type.id, type]));
  const rows: NotificationRow[] = [];

  for (const request of observedRequests) {
    const context = request.account_proposal_id ? contextByAccount.get(request.account_proposal_id) : undefined;
    const schedule = context ? scheduleBySlug.get(context.platform_slug) : scheduleByManifest.get(request.manifest_id);
    if (!schedule) {
      continue;
    }
    const owner = request.local_worker_id
      ? workerName(workerById.get(request.local_worker_id) ?? null)
      : request.local_company_id
        ? companyById.get(request.local_company_id)?.name ?? request.external_entity_label ?? "Empresa"
        : request.external_entity_label ?? "Entidad externa";
    const typeName = request.document_type_id
      ? typeById.get(request.document_type_id)?.name ?? request.external_requirement_label
      : request.external_requirement_label;
    rows.push({
      key: `observed-request:${request.id}`,
      platform_slug: context?.platform_slug ?? schedule.platform_slug,
      platform_name: context?.platform_name ?? schedule.platform_name,
      context: context?.trace_label ?? request.external_entity_label ?? "Contexto leido",
      severity: request.severity,
      title: `${typeName}: ${request.external_status}`,
      detail: [
        owner,
        request.rejection_reason ?? request.external_comment,
        `Confianza ${formatConfidence(request.confidence)}`
      ]
        .filter(Boolean)
        .join(" / "),
      action: request.matched_document_version_id
        ? "Documento disponible en Hub: preparar subida con preview y aprobacion."
        : "Falta documento equivalente en Hub: cargar o crear tipo documental.",
      source: "Lectura externa normalizada",
      sourceKind: "observed",
      createdAt: request.last_seen_at,
      localPath: request.local_worker_id || request.local_company_id ? "/arm" : undefined,
      scheduleId: schedule.id,
      accountProposalId: request.account_proposal_id
    });
  }

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
        sourceKind: "platform",
        createdAt: schedule.last_run_at ?? schedule.next_run_at,
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
        sourceKind: "surface",
        createdAt: schedule.last_run_at ?? schedule.next_run_at,
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
        sourceKind: "schedule",
        createdAt: schedule.last_run_at ?? schedule.next_run_at,
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
      sourceKind: "incident",
      createdAt: schedule.last_run_at ?? schedule.next_run_at,
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
        sourceKind: "schedule",
        createdAt: schedule.last_run_at ?? schedule.next_run_at,
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
    return {
      key: `evidence:${intake.id}`,
      intake,
      owner,
      typeName,
      createdAt: intake.created_at ?? intake.reviewed_at
    };
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

function workerName(worker: Worker | null) {
  if (!worker) {
    return "Trabajador";
  }
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

function isOlderThan(value: string | null, minimumDate: string) {
  if (!value || !minimumDate) {
    return false;
  }
  const rowTime = new Date(value).getTime();
  const minimumTime = new Date(`${minimumDate}T00:00:00`).getTime();
  return Number.isFinite(rowTime) && Number.isFinite(minimumTime) && rowTime < minimumTime;
}

function matchesQuery(query: string, values: Array<string | null | undefined>) {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    return true;
  }
  return values
    .filter(Boolean)
    .join(" ")
    .toLowerCase()
    .includes(normalized);
}

function formatDateTime(value: string | null) {
  if (!value) {
    return "Sin fecha";
  }
  return new Date(value).toLocaleString("es-ES");
}

function formatDate(value: string) {
  return new Date(`${value}T00:00:00`).toLocaleDateString("es-ES");
}

function readDismissedRows() {
  if (typeof window === "undefined") {
    return {};
  }
  const raw = window.localStorage.getItem(dismissedStorageKey);
  if (!raw) {
    return {};
  }
  try {
    return JSON.parse(raw) as Record<string, DismissedNotification>;
  } catch {
    window.localStorage.removeItem(dismissedStorageKey);
    return {};
  }
}

function writeDismissedRows(rows: Record<string, DismissedNotification>) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(dismissedStorageKey, JSON.stringify(rows));
}

function isErrorMessage(message: string) {
  return message.startsWith("HTTP") || message.startsWith("No se") || message.startsWith("Invalid") || message.includes("error") || message.includes("token");
}
